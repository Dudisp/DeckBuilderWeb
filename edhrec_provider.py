from typing import Any

try:
    from pyedhrec import EDHRec
except Exception:
    EDHRec = None  # runtime import error will be surfaced when used


class ClientProvidedEdhrecProvider:
    """
    Uses data fetched on the client (browser) side. Expects a payload with:
    {
        "avg_deck": {"Card Name": qty, ...}  # required
        "card_list": {"cards": {cardName: {"primary_type": "Creature", ...}, ...}}  # optional but recommended
        "top_cards_by_type": {"Creature": [{"name": "...", "primary_type": "Creature", "color_identity": []}, ...]}
        "similar": {"Missing Card": [{"name": "...", "color_identity": []}, ...]}
        "card_details": {"Card Name": {"type": "...", "primary_type": "...", "color_identity": [...]}}
    }
    """

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload or {}

    def _require(self, key: str):
        if key not in self.payload:
            raise KeyError(f"Missing '{key}' in provided EDHRec payload")
        return self.payload[key]

    def get_avg_deck(self, commander_name: str, theme: str | None, budget_type) -> dict[str, int]:
        deck = self._require("avg_deck")
        # Accept list of {"name":..., "count":...} or dict
        if isinstance(deck, list):
            return {item["name"]: int(item["count"]) for item in deck}
        return {name: int(count) for name, count in deck.items()}

    def get_card_list(self, card_names: list[str]) -> dict:
        card_list = self.payload.get("card_list", {})
        # Optional filtering by requested names to reduce payload size
        if card_names and card_list.get("cards"):
            filtered = {name: card_list["cards"].get(name) for name in card_names if name in card_list["cards"]}
            return {"cards": filtered}
        return card_list

    def get_top_cards_for_type(self, commander_name: str, card_type: str) -> list[dict[str, Any]]:
        top_cards_by_type = self.payload.get("top_cards_by_type", {})
        return top_cards_by_type.get(card_type, [])

    def get_similar(self, card_name: str) -> list[dict[str, Any]]:
        similar = self.payload.get("similar", {})
        return similar.get(card_name, [])

    def get_card_details(self, card_name: str) -> dict[str, Any]:
        details = self.payload.get("card_details", {})
        if card_name in details:
            return details[card_name]
        raise KeyError(f"Missing card details for '{card_name}' in provided EDHRec payload")


class ServerEdhrecProvider:
    """Provider that performs EDHRec calls server-side using pyedhrec."""

    def __init__(self):
        if EDHRec is None:
            raise RuntimeError("pyedhrec is required for server-side EDHRec provider; install pyedhrec in requirements.txt")
        self.edhrec = EDHRec()

    def get_avg_deck(self, commander_name: str, theme: str | None, budget_type) -> dict[str, int]:
        # Mirrors old_main.get_commanders_average_deck_with_theme
        average_deck_uri, params = self.edhrec._build_nextjs_uri("average-decks", commander_name, theme=theme, budget=budget_type.value if hasattr(budget_type, 'value') else budget_type)
        res = self.edhrec._get(average_deck_uri, query_params=params)
        data = self.edhrec._get_nextjs_data(res)
        deck = data.get("deck") or []
        # deck may be list of strings like '2 Card Name' or list of dicts
        result = {}
        if isinstance(deck, list):
            for item in deck:
                if isinstance(item, str):
                    parts = item.split(' ')
                    if parts and parts[0].isdigit():
                        qty = int(parts[0])
                        name = ' '.join(parts[1:])
                        result[name] = qty
                elif isinstance(item, dict) and 'name' in item and 'count' in item:
                    result[item['name']] = int(item['count'])
        elif isinstance(deck, dict):
            for name, count in deck.items():
                result[name] = int(count)
        return result

    def get_card_list(self, card_names: list[str]) -> dict:
        # EDHRec client has a helper get_card_list
        try:
            return self.edhrec.get_card_list(card_names)
        except Exception:
            # fallback: return empty structure
            return {"cards": {}}

    def get_top_cards_for_type(self, commander_name: str, card_type: str) -> list[dict[str, Any]]:
        # Map type to pyedhrec helper methods where possible
        try:
            raw = None
            match card_type:
                case "Creature":
                    raw = self.edhrec.get_top_creatures(commander_name)
                case "Sorcery":
                    raw = self.edhrec.get_top_sorceries(commander_name)
                case "Land":
                    raw = self.edhrec.get_top_lands(commander_name)
                case "Instant":
                    raw = self.edhrec.get_top_instants(commander_name)
                case "Enchantment":
                    raw = self.edhrec.get_top_enchantments(commander_name)
                case "Artifact":
                    raw = self.edhrec.get_top_artifacts(commander_name)
                case "Planeswalker":
                    raw = self.edhrec.get_top_planeswalkers(commander_name)
                case "Battle":
                    raw = self.edhrec.get_top_battles(commander_name)
                case _:
                    raw = []

            # Normalize raw into a list[dict] where each dict has at least {'name': ...}
            def normalize_item(item):
                # if item is a string, treat as name
                if isinstance(item, str):
                    return {"name": item}
                if isinstance(item, dict):
                    # common shape: {'name': 'Foo', ...}
                    if 'name' in item:
                        return item
                    # sometimes it's keyed by name: {'Foo': {...}}
                    if len(item) == 1:
                        k, v = next(iter(item.items()))
                        if isinstance(v, dict):
                            out = dict(v)
                            out['name'] = k
                            return out
                    # fallback: return as-is
                    return item
                # unknown -> None
                return None

            out_list: list[dict[str, Any]] = []
            if raw is None:
                return []

            if isinstance(raw, list):
                for it in raw:
                    ni = normalize_item(it)
                    if ni:
                        out_list.append(ni)
                return out_list

            if isinstance(raw, dict):
                # If dict values are lists, flatten them
                for v in raw.values():
                    if isinstance(v, list):
                        for it in v:
                            ni = normalize_item(it)
                            if ni:
                                out_list.append(ni)
                        if out_list:
                            return out_list
                # Otherwise, try to interpret keys as names
                for k, v in raw.items():
                    if isinstance(v, dict):
                        ni = dict(v)
                        ni.setdefault('name', k)
                        out_list.append(ni)
                    elif isinstance(v, str):
                        out_list.append({'name': v})
                if out_list:
                    return out_list

            # unknown shape -> empty
            return []
        except Exception:
            return []

    def get_similar(self, card_name: str) -> list[dict[str, Any]]:
        # Mirrors old_main.get_similar
        try:
            card_name_fixed = card_name
            average_deck_uri, params = self.edhrec._build_nextjs_uri("cards", card_name_fixed, card_name_fixed)
            params.pop("commanderName", None)
            res = self.edhrec._get(average_deck_uri, query_params=params)
            data = self.edhrec._get_nextjs_data(res)
            return data.get("similar", [])
        except Exception:
            return []

    def get_card_details(self, card_name: str) -> dict[str, Any]:
        try:
            return self.edhrec.get_card_details(card_name)
        except Exception as e:
            raise KeyError(str(e))
