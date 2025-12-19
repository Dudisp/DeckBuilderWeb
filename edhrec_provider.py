from typing import Any, Protocol


class EdhrecProvider(Protocol):
    def get_avg_deck(self, commander_name: str, theme: str | None, budget_type: Any) -> dict[str, int]:
        ...

    def get_card_list(self, card_names: list[str]) -> dict:
        ...

    def get_top_cards_for_type(self, commander_name: str, card_type: str) -> list[dict[str, Any]]:
        ...

    def get_similar(self, card_name: str) -> list[dict[str, Any]]:
        ...

    def get_card_details(self, card_name: str) -> dict[str, Any]:
        ...


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


try:
    from pyedhrec import EDHRec
except ImportError:  # pragma: no cover - optional dependency for CLI use
    EDHRec = None


class ServerEdhrecProvider:
    """Fallback provider that uses pyedhrec (server-side). Not used when client data is supplied."""

    def __init__(self):
        if EDHRec is None:
            raise RuntimeError("pyedhrec is not installed; cannot use ServerEdhrecProvider")
        self.edhrec = EDHRec()

    def get_avg_deck(self, commander_name: str, theme: str | None, budget_type) -> dict[str, int]:
        avg_deck = dict()
        commander_avg_deck = self.edhrec.get_commanders_average_deck_with_theme(
            card_name=commander_name, theme=theme, budget=budget_type.value
        )
        decklist = commander_avg_deck.get("decklist")
        if decklist:
            for item in decklist:
                split = item.split(" ")
                avg_deck[" ".join(split[1:])] = int(split[0])
        return avg_deck

    def get_card_list(self, card_names: list[str]) -> dict:
        return self.edhrec.get_card_list(card_names)

    def get_top_cards_for_type(self, commander_name: str, card_type: str) -> list[dict[str, Any]]:
        match card_type:
            case "Creature":
                top_cards = self.edhrec.get_top_creatures(commander_name)
            case "Sorcery":
                top_cards = self.edhrec.get_top_sorceries(commander_name)
            case "Land":
                top_cards = self.edhrec.get_top_lands(commander_name)
            case "Instant":
                top_cards = self.edhrec.get_top_instants(commander_name)
            case "Enchantment":
                top_cards = self.edhrec.get_top_enchantments(commander_name)
            case "Artifact":
                top_cards = self.edhrec.get_top_artifacts(commander_name)
            case "Planeswalker":
                top_cards = self.edhrec.get_top_planeswalkers(commander_name)
            case "Battle":
                top_cards = self.edhrec.get_top_battles(commander_name)
            case _:
                top_cards = {}
        return list(top_cards.values())[0] if top_cards else []

    def get_similar(self, card_name: str) -> list[dict[str, Any]]:
        return self.edhrec.get_similar(card_name)

    def get_card_details(self, card_name: str) -> dict[str, Any]:
        return self.edhrec.get_card_details(card_name)

