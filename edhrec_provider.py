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

