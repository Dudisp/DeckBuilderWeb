import csv
import logging
import random
from collections import defaultdict
from enum import Enum
from typing import Any, TextIO

from unidecode import unidecode
from edhrec_provider import EdhrecProvider

COLOR_TO_BASIC_LAND = {
    "W": "Plains",
    "U": "Island",
    "B": "Swamp",
    "R": "Mountain",
    "G": "Forest",
}


class BudgetType(Enum):
    REGULAR = None
    BUDGET = "budget"
    EXPANSIVE = "expansive"


class CardType(Enum):
    CREATURE = "Creature"
    SORCERY = "Sorcery"
    LAND = "Land"
    INSTANT = "Instant"
    ENCHANTMENT = "Enchantment"
    ARTIFACT = "Artifact"
    PLANESWALKER = "Planeswalker"
    BATTLE = "Battle"


def get_inventory() -> dict[str, dict[str, str]]:
    inventory: dict[str, dict[str, str]] = dict()

    with open("inventory.csv", newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            inventory[unidecode(row["Name"]).split(" // ")[0]] = row

        return inventory


class DeckBuilder:
    def __init__(self, inventory_file: TextIO, edhrec_provider: EdhrecProvider):
        self.edhrec_provider = edhrec_provider
        self.inventory = self.get_inventory(inventory_file)
        self.logger = logging.getLogger(__name__)

    def get_inventory(self, inventory_file) -> dict[str, dict[str, str]]:
        inventory: dict[str, dict[str, str]] = dict()
        reader = csv.DictReader(inventory_file)
        for row in reader:
            inventory[unidecode(row["Name"]).split(" // ")[0]] = row

        return inventory

    def get_avg_budget_deck(self, commander_name: str, theme: str = None) -> dict[str, int]:
        return self.get_avg_deck(commander_name, theme, BudgetType.BUDGET)

    def get_avg_expansive_deck(self, commander_name: str, theme: str = None) -> dict[str, int]:
        return self.get_avg_deck(commander_name, theme, BudgetType.EXPANSIVE)

    def get_avg_deck(self, commander_name: str, theme: str = None, budget_type: BudgetType = BudgetType.REGULAR) -> dict[str, int]:
        return self.edhrec_provider.get_avg_deck(commander_name, theme, budget_type)

    def build_new_deck_from_inventory(self, avg_deck: dict[str, int]) -> tuple[dict[str, int], list[str]]:
        new_deck = dict()
        unavailable_cards = list()
        for name, number in avg_deck.items():
            if unidecode(name) in self.inventory or name in COLOR_TO_BASIC_LAND.values():
                new_deck[unidecode(name)] = number
            else:
                unavailable_cards.append(name)
        return new_deck, unavailable_cards

    def _get_deck_size(self, deck: dict[str, int]) -> int:
        return sum(deck.values())

    def sort_cards_by_type(self, card_details_list: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
        card_detail_groups = defaultdict(list)
        for name, card_details in card_details_list.items():
            card_detail_groups[card_details['primary_type']].append(card_details)

        return dict(card_detail_groups)

    def fill_in_from_high_synergy_cards(self, commander_name: str, unavailable_cards_by_type: dict[str, list[str]], new_deck: dict[str, int]):
        # high_synergy_cards = edhrec.get_high_synergy_cards(commander_name)
        extra_cards_by_type = dict()
        for card_type, missing_cards in unavailable_cards_by_type.items():
            top_cards = self.get_top_cards_for_card_type(commander_name, card_type)
            top_cards = list(filter(lambda card: card['name'] not in new_deck and card['name'] in self.inventory, top_cards))
            replacement_cards, extra_cards = top_cards[0: len(missing_cards)], top_cards[len(missing_cards): len(top_cards)]
            extra_cards_by_type[card_type] = extra_cards
            for card in replacement_cards:
                new_deck[card['name']] = 1
        return extra_cards_by_type

    def get_top_cards_for_card_type(self, commander_name: str, card_type: str) -> list[dict[str, Any]]:
        match card_type:
            case CardType.CREATURE.value:
                top_cards = self.edhrec_provider.get_top_cards_for_type(commander_name, CardType.CREATURE.value)
            case CardType.SORCERY.value:
                top_cards = self.edhrec_provider.get_top_cards_for_type(commander_name, CardType.SORCERY.value)
            case CardType.LAND.value:
                top_cards = self.edhrec_provider.get_top_cards_for_type(commander_name, CardType.LAND.value)
            case CardType.INSTANT.value:
                top_cards = self.edhrec_provider.get_top_cards_for_type(commander_name, CardType.INSTANT.value)
            case CardType.ENCHANTMENT.value:
                top_cards = self.edhrec_provider.get_top_cards_for_type(commander_name, CardType.ENCHANTMENT.value)
            case CardType.ARTIFACT.value:
                top_cards = self.edhrec_provider.get_top_cards_for_type(commander_name, CardType.ARTIFACT.value)
            case CardType.PLANESWALKER.value:
                top_cards = self.edhrec_provider.get_top_cards_for_type(commander_name, CardType.PLANESWALKER.value)
            case CardType.BATTLE.value:
                top_cards = self.edhrec_provider.get_top_cards_for_type(commander_name, CardType.BATTLE.value)
            case _:
                top_cards = []
        return top_cards

    def get_similar(self, card_name: str) -> dict:
        card_name = self._fix_card_name(card_name)
        return self.edhrec_provider.get_similar(card_name)

    def _is_color_identity_match(self, card_color_identity: list[str], commander_color_identity: list[str]) -> bool:
        return set(card_color_identity) <= set(commander_color_identity)

    def find_similar_cards(self, commander: str, partner: str | None, unavailable_cards: list[str], new_deck: dict[str, int]) -> tuple[dict[str, int], list[str]]:
        still_unavailable_cards = []
        commander_color_identity = self._get_color_identity(commander, partner)
        
        for counter, unavailable_card in enumerate(unavailable_cards, 1):
            self.logger.info(f"Checking {counter}/{len(unavailable_cards)} - {unavailable_card}")
            if self._find_similar_card(unavailable_card, commander_color_identity, new_deck):
                continue

            card_details = self.edhrec_provider.get_card_details(self._fix_card_name(unavailable_card))
            if card_details["type"] == CardType.LAND.value:
                self.logger.info(f"{unavailable_card} is a land, replace with Basic Land")
                self._add_basic_land_to_deck(commander_color_identity, new_deck)
            else:
                still_unavailable_cards.append(unavailable_card)
                self.logger.info(f"Did not find a replacement for {unavailable_card}")
        
        return new_deck, still_unavailable_cards
    
    def _get_color_identity(self, commander: str, partner: str | None) -> list[str]:
        color_identity = self.edhrec_provider.get_card_details(commander)["color_identity"]
        if partner:
            partner_color_identity = self.edhrec_provider.get_card_details(partner)["color_identity"]
            color_identity = list(set(color_identity).union(partner_color_identity))
        return color_identity

    def _find_similar_card(self, unavailable_card: str, commander_color_identity: list[str], new_deck: dict[str, int]) -> bool:
        similars = self.get_similar(unavailable_card)
        for similar in similars:
            if (self._is_color_identity_match(similar["color_identity"], commander_color_identity) and
                similar["name"] not in new_deck and similar["name"] in self.inventory):
                new_deck[similar["name"]] = 1
                self.logger.info(f"Found {similar['name']} similar to {unavailable_card}")
                return True
        return False
    
    def _fix_card_name(self, unavailable_card: str) -> str:
        return unidecode(unavailable_card).replace(" // ", "-").replace(":", "")

    def _add_basic_land_to_deck(self, color_identity: list[str], new_deck: dict[str, int]) -> None:
        color = random.choice(color_identity)
        basic_land = COLOR_TO_BASIC_LAND[color]
        if basic_land in new_deck:
            new_deck[basic_land] += 1
        else:
            new_deck[basic_land] = 1

    def build(self, commander: str, partner: str = None, theme: str = None, budget_type: BudgetType = BudgetType.REGULAR):
        if partner:
            commander_name = f"{commander}-{partner}"
        else:
            commander_name = commander
        # Get the average decklist for a commander
        avg_deck = self.get_avg_deck(commander_name, theme, budget_type)

        if not avg_deck and partner:
            commander_name = f"{partner}-{commander}"

            avg_deck = self.get_avg_deck(commander_name, theme, budget_type)

        new_deck, unavailable_cards = self.build_new_deck_from_inventory(avg_deck)
        new_deck, unavailable_cards = self.find_similar_cards(commander, partner, unavailable_cards, new_deck)

        unavailable_cards_by_type = {}
        extra_cards_by_type = {}
        if unavailable_cards:
            card_list = self.edhrec_provider.get_card_list(unavailable_cards)
            unavailable_cards_by_type = self.sort_cards_by_type(card_list['cards'])
            extra_cards_by_type = self.fill_in_from_high_synergy_cards(commander_name, unavailable_cards_by_type, new_deck)

        self._print_deck(new_deck)

        return {
            "deck": new_deck,
            "deck_size": self._get_deck_size(new_deck),
            "unavailable_cards": unavailable_cards,
            "unavailable_cards_by_type": unavailable_cards_by_type,
            "extra_cards_by_type": extra_cards_by_type,
        }

    def _print_deck(self, new_deck):
        print("Deck:")
        for name, number in new_deck.items():
            print(f"{number} {name}")
        size = self._get_deck_size(new_deck)
        print(f"Deck total size: {size}")
