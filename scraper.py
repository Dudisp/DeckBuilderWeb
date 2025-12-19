import csv
import time
from collections import defaultdict
from enum import Enum

import requests
import scrython
from bs4 import BeautifulSoup
from unidecode import unidecode

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


EDH_TYPE_TO_CARD_TYPE = {
    "creatures": CardType.CREATURE.value,
    "instants": CardType.INSTANT.value,
    "sorceries": CardType.SORCERY.value,
    "enchantments": CardType.ENCHANTMENT.value,
    "planeswalkers": CardType.PLANESWALKER.value,
    "utilitylands": CardType.LAND.value,
    "lands": CardType.LAND.value,
    "utilityartifacts": CardType.ARTIFACT.value,
    "manaartifacts": CardType.ARTIFACT.value,
}

CARD_TYPES_TO_PROCESS = list(EDH_TYPE_TO_CARD_TYPE.keys())


def get_inventory() -> dict[str, dict[str, str]]:
    inventory: dict[str, dict[str, str]] = dict()

    with open("inventory.csv", newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            inventory[unidecode(row["Name"]).split(" // ")[0]] = row

        return inventory


def get_decklist(edhrec_deck_page: str) -> dict[str, int] | None:
    decklist: dict[str, int] = {}

    response = requests.get(edhrec_deck_page)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    div = soup.find("div", class_="DecklistPanel_code__pZfEA")
    code = div.find("code") if div else None
    content = code.text if code else None

    if not content:
        return None

    for line in content.split("\n"):
        line_arr = line.strip().split(" ")
        if not line_arr[0].isdigit():
            continue
        amount = int(line_arr[0])
        card_name = " ".join(line_arr[1:])
        decklist[card_name] = amount

    return decklist


def get_card_data(edhrec_card_page: str) -> dict[str, list[str]]:
    card_data = defaultdict(list)

    response = requests.get(edhrec_card_page)
    if response.status_code != 200:
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    type_divs = soup.find_all("div", class_="Grid_cardlist__AXXsz")

    for type_div in type_divs:
        edh_card_type = type_div.get("id")
        if edh_card_type in CARD_TYPES_TO_PROCESS:
            grid = type_div.find("div")
            if not grid:
                continue
            card_grid = grid.find("div", class_="Grid_grid__EAPIs")
            if not card_grid:
                continue
            card_divs = card_grid.find_all("div", class_="d-flex")

            cards = []
            for card_div in card_divs:
                name_container = card_div.find("div", class_="Card_container__Ng56K")
                if not name_container:
                    continue
                name_wrapper = name_container.find("div", class_="Card_nameWrapper__oeNTe")
                if not name_wrapper:
                    continue
                card_name = name_wrapper.text.strip()
                cards.append(card_name)

            card_type = EDH_TYPE_TO_CARD_TYPE.get(edh_card_type)
            if card_type:
                card_data[card_type].extend(cards)

    return dict(card_data)


def filter_cards_not_in_inventory(inventory: dict[str, dict[str, str]], card_data: dict[str, list[str]]):
    for card_type in card_data.keys():
        card_data[card_type] = [card for card in card_data[card_type] if card in inventory]
    return card_data


def write_deck_to_csv(decklist: dict[str, int]) -> None:
    headers = ["Amount", "Name"]
    with open("deck.csv", "w", newline="") as file:
        writer = csv.writer(file)

        # Write headers
        writer.writerow(headers)

        # Write data rows
        for name, amount in decklist.items():
            writer.writerow([amount, name])


def get_deck_from_inventory(inventory: dict[str, dict[str, str]], decklist: dict[str, int], card_data: dict[str, list[str]]) -> tuple[dict[str, int], dict[str, list[str]]]:
    inventory_deck = dict()
    filtered_out = defaultdict(list)
    for name, amount in decklist.items():
        if name in inventory or name in COLOR_TO_BASIC_LAND.values():
            inventory_deck[name] = amount
        else:
            type = get_card_type(name)
            filtered_out[type].append(name)

    # filter out cards that are already in deck
    for card_type in card_data.keys():
        card_data[card_type] = [card for card in card_data[card_type] if card not in decklist]

    for card_type, cards in dict(filtered_out).items():
        number_of_filtered_cards = len(cards)
        replacement_cards = card_data[card_type]
        add_cards_to_deck(inventory_deck, number_of_filtered_cards, replacement_cards)
        if card_type == CardType.LAND.value:
            add_basic_lands_to_deck(inventory_deck, number_of_filtered_cards, len(replacement_cards))

    return inventory_deck, dict(filtered_out)


def add_cards_to_deck(decklist: dict[str, int], number_of_filtered_cards: int, replacement_cards: list[str]) -> None:
    for card in replacement_cards[:number_of_filtered_cards]:
        decklist[card] = 1


def add_basic_lands_to_deck(decklist: dict[str, int], number_of_filtered_cards: int, number_of_replacement_cards: int):
    if number_of_filtered_cards > number_of_replacement_cards:
        decklist["basic land"] = number_of_filtered_cards - number_of_replacement_cards


def get_card_type(card_name: str) -> str | None:
    time.sleep(0.1)
    card = scrython.cards.Named(fuzzy=card_name)
    type = get_type_from_type_line(card.type_line())
    if type is None:
        print(f"Could not find type for {card.name()}")
        return None
    return type.value


def get_type_from_type_line(type_line: str) -> CardType | None:
    for item in CardType:
        # print(item.name, item.value)
        if item.value in type_line:
            return item
    return None


def build_deck_scraper(inventory: dict[str, dict[str, str]], commander_link: str, edhrec_deck_page: str) -> dict[str, int]:
    deck = get_decklist(edhrec_deck_page=edhrec_deck_page)
    card_data = get_card_data(edhrec_card_page=commander_link)
    card_data = filter_cards_not_in_inventory(inventory=inventory, card_data=card_data)
    deck, filtered_out = get_deck_from_inventory(inventory=inventory, decklist=deck, card_data=card_data)
    return deck


if __name__ == '__main__':
    edhrec_card_page = "https://edhrec.com/commanders/shilgengar-sire-of-famine/angels"
    edhrec_deck_page = "https://edhrec.com/average-decks/shilgengar-sire-of-famine/angels"
    inventory = get_inventory()
    deck = build_deck_scraper(inventory, edhrec_card_page, edhrec_deck_page)
    write_deck_to_csv(decklist=deck)
    print(deck)
