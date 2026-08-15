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
    "Herbs",
    "Melee Weapons",
    "Ranged",
    "Magic",
    "Armor",
    "Bones & Hides",
    "Gems & Jewelry",
    "Potions & Brews",
    "Tools",
    "Construction",
    "Misc",
]

COOKED_FOOD = frozenset({
    "lobster", "shark", "salmon", "tuna", "swordfish", "monkfish", "herring",
    "mackerel", "shrimp", "trout", "sardine", "cooked_rat_meat", "cooked_mutton",
    "cooked_beef", "cooked_chicken", "corn", "cabbage", "onion", "carrot",
    "pumpkin", "watermelon", "strawberry", "tomato", "potato",
    "dragon_fruit", "golden_wheat", "starfruit",
})

GEMS = frozenset({
    "emerald", "sapphire", "ruby", "diamond", "black_pearl",
})

JEWELRY = frozenset({
    "archers_ring", "tower_ring", "gold_ring", "diamond_ring", "gold_ruby_ring",
    "kraken_tentacle", "tormented_necklace", "tower_amulet",
})

HERBS = frozenset({
    "magic_herb", "spirit_herb", "celestial_bloom",
})

CONSTRUCTION = frozenset({
    "oak_bookshelf", "willow_cabinet", "wooden_rack", "wooden_shelf",
    "stone_block", "plank",
})

MELEE_SUFFIXES = (
    "_sword", "_dagger", "_scimitar", "_longsword", "_battleaxe",
    "_warhammer", "_mace", "_spear", "_halberd", "_claws", "_2h_sword",
)

ARMOR_PARTS = (
    "_helmet", "_helm", "_platebody", "_platelegs", "_plateskirt", "_boots",
    "_shield", "_kiteshield", "_gloves", "_cape", "_body", "_legs",
    "_mail", "_hood", "_hat", "_robe", "_amulet",
)

RANGED_PARTS = ("bow", "shortbow", "longbow", "crossbow", "arrow", "bolt")

TOOL_SUFFIXES = ("_pickaxe", "_hoe", "_fishing_rod")


def categorize_item(key: str) -> str:
    k = key.lower()

    if k == "coins" or k == "carnival_ticket" or k == "ancient_treasure":
        return "Currency"

    if k.endswith("_ore") or k in ("coal", "rune_essence", "stone", "carved_stone", "tin_ore"):
        return "Ores & Mining"

    if k.endswith("_bar") or k.endswith("_nail"):
        return "Bars & Smithing"

    if k in ("log", "plank", "ashes") or k.endswith("_log") or k.endswith("_plank") or k.endswith("_ashes"):
        return "Wood & Planks"

    if k.endswith("_rune"):
        return "Runes"

    if k.startswith("raw_"):
        return "Raw Food"

    if k.startswith("cooked_") or k in COOKED_FOOD:
        return "Cooked Food"

    if k.endswith("_seed") or k == "magic_bean":
        return "Seeds & Farming"

    if k in HERBS or k.endswith("_herb"):
        return "Herbs"

    if any(k.endswith(s) for s in TOOL_SUFFIXES) or (k.endswith("_axe") and not k.endswith("_battleaxe")):
        return "Tools"

    if any(k.endswith(s) for s in MELEE_SUFFIXES):
        return "Melee Weapons"

    if any(p in k for p in RANGED_PARTS):
        return "Ranged"

    if k.endswith("_staff") or k.endswith("_wand") or k.endswith("_tome") or k.startswith("staff_"):
        return "Magic"

    if any(p in k for p in ARMOR_PARTS) or k in ("goblin_mail",):
        return "Armor"

    if (
        "bone" in k or k.endswith("_hide") or k.endswith("_silk")
        or k.endswith("_fang") or k.endswith("_horn") or k.endswith("_scale")
        or k == "rotten_flesh"
    ):
        return "Bones & Hides"

    if k in GEMS or k in JEWELRY or k.endswith("_necklace") or k.endswith("_ring") or k.startswith("ring_"):
        return "Gems & Jewelry"

    if k.endswith("_potion") or k.endswith("_brew"):
        return "Potions & Brews"

    if k in CONSTRUCTION or k.endswith("_bookshelf") or k.endswith("_cabinet") or k.endswith("_shelf") or k.endswith("_rack"):
        return "Construction"

    if k == "lockpick":
        return "Tools"

    return "Misc"


def category_sort_key(category: str) -> int:
    try:
        return CATEGORY_ORDER.index(category)
    except ValueError:
        return len(CATEGORY_ORDER)
