"""Item category heuristics for Idle Fantasy save inventory."""

from __future__ import annotations

CATEGORY_ORDER = [
    "Currency",
    "Ores & Mining",
    "Bars & Smithing",
    "Wood & Planks",
    "Runes",
    "Raw Food",
    "Cooked Food",
    "Seeds & Farming",
    "Melee Weapons",
    "Ranged",
    "Magic",
    "Armor",
    "Bones & Hides",
    "Gems & Jewelry",
    "Potions & Brews",
    "Misc",
]

COOKED_FOOD = frozenset({
    "lobster", "shark", "salmon", "tuna", "swordfish", "monkfish", "herring",
    "mackerel", "shrimp", "trout", "sardine", "cooked_rat_meat", "cooked_mutton",
    "cooked_beef", "cooked_chicken", "corn", "cabbage", "onion", "carrot",
    "pumpkin", "watermelon", "strawberry", "tomato", "potato",
})

GEMS = frozenset({
    "emerald", "sapphire", "ruby", "diamond", "black_pearl",
})

MELEE_SUFFIXES = (
    "_sword", "_axe", "_dagger", "_scimitar", "_longsword", "_battleaxe",
    "_warhammer", "_mace", "_spear", "_halberd", "_claws",
)

ARMOR_PARTS = (
    "_helmet", "_platebody", "_platelegs", "_plateskirt", "_boots",
    "_shield", "_kiteshield", "_gloves", "_cape", "_body", "_legs",
    "_mail", "_hood", "_hat", "_robe", "_amulet",
)

RANGED_PARTS = ("bow", "shortbow", "longbow", "crossbow", "arrow", "bolt")


def categorize_item(key: str) -> str:
    k = key.lower()

    if k == "coins" or k == "carnival_ticket":
        return "Currency"

    if k.endswith("_ore") or k in ("coal", "rune_essence", "stone", "carved_stone", "tin_ore"):
        return "Ores & Mining"

    if k.endswith("_bar") or k.endswith("_nail"):
        return "Bars & Smithing"

    if k.endswith("_log") or k.endswith("_plank") or k.endswith("_ashes"):
        return "Wood & Planks"

    if k.endswith("_rune"):
        return "Runes"

    if k.startswith("raw_"):
        return "Raw Food"

    if k.startswith("cooked_") or k in COOKED_FOOD:
        return "Cooked Food"

    if k.endswith("_seed") or k == "magic_bean":
        return "Seeds & Farming"

    if any(k.endswith(s) for s in MELEE_SUFFIXES):
        return "Melee Weapons"

    if any(p in k for p in RANGED_PARTS):
        return "Ranged"

    if k.endswith("_staff") or k.endswith("_wand") or k.endswith("_tome"):
        return "Magic"

    if any(p in k for p in ARMOR_PARTS) or k in ("goblin_mail",):
        return "Armor"

    if "bone" in k or k.endswith("_hide") or k.endswith("_silk") or k.endswith("_fang") or k.endswith("_horn"):
        return "Bones & Hides"

    if k in GEMS or k.endswith("_necklace") or k.startswith("ring_"):
        return "Gems & Jewelry"

    if k.endswith("_potion") or k.endswith("_brew"):
        return "Potions & Brews"

    if k.endswith("_pickaxe") or k.endswith("_axe") and not k.endswith("_battleaxe"):
        # pickaxe/hoe/fishing_rod handled as tools -> Misc unless caught above
        pass

    return "Misc"


def category_sort_key(category: str) -> int:
    try:
        return CATEGORY_ORDER.index(category)
    except ValueError:
        return len(CATEGORY_ORDER)
