"""Smoke tests for save parsing against current Idle Fantasy exports."""

from __future__ import annotations

import unittest
from pathlib import Path

from categories import categorize_item
from parser import normalize_save, parse_save_file
from validation import analyze_save


def _save(**overrides) -> dict:
    base = {
        "exported_at": 1_700_000_000_000,
        "coins": 100,
        "sig": "abc123",
        "skillLevels": {"mining": 10, "agility": 99},
        "skillXp": {"mining": 1000, "agility": 14_000_000},
        "inventory": {
            "iron_ore": 50,
            "slayer_helm": 1,
            "mithril_pickaxe": 1,
            "staff_of_fire": 1,
            "archers_ring": 2,
            "magic_herb": 4,
            "oak_bookshelf": 1,
        },
        "equipped": {"head": "slayer_helm"},
        "flags": {
            "character_name": "Tester",
            "ironman": False,
            "equipped_title": "godslayer",
            "unlocked_titles": ["godslayer", "devout"],
            "skill_prestige": {"agility": 3},
            "prestige_points_earned": {"agility": 9, "attack": 3},
            "prestige_nodes": {"agility": ["agility_endurance_1"]},
            "tower_current_floor": 80,
            "tower_best_floor": 86,
            "tower_milestones": [10, 20],
            "tower_xp_bonus_pct": 3,
            "tower_hp_bonus": 5,
            "tower_coin_bonus_pct": 0,
            "hired_worker": {"tier": "MASTER", "daily_name": "Ymir", "session_queue": []},
            "armor_loadouts": {"magic": {"head": "slayer_helm", "cape": "magic_cape"}},
            "active_slayer_task": {
                "enemy_key": "hellhound",
                "target_kills": 13,
                "kills_completed": 4,
                "xp_per_kill": 78,
                "task_points": 9,
            },
            "foretelled_tasks": [
                {"enemy_key": "goblin", "target_kills": 32, "kills_completed": 0, "xp_per_kill": 15, "task_points": 3},
            ],
            "town_building_tiers": {"inn": 2, "garden": 1},
            "monument_tier": 2,
            "monument_fund": 0,
            "seasonal_tokens_by_event": {"sunspire_solstice_2026": 125},
            "seasonal_bounty_slots": ["sunspire_firewood"],
            "seasonal_bounty_progress": {"sunspire_firewood": 20},
            "player_notes": "  next: willow logs  ",
            "magic_loadout_spell_name": "blood_wave",
            "equipped_food": {"lobster": 1, "shark": 2},
            "equipped_arrows": "mithril_arrows",
            "food_eat_threshold_pct": 60,
            "boss_coin_day": 20260714,
            "boss_coin_kills_by_boss": {"demon_lord": 5, "void_sovereign": 2},
            "active_boss_repeat_index": 2,
            "active_boss_repeat_total": 5,
            "house": {
                "rooms": [{"x": 7, "y": 7, "w": 4, "h": 4, "floor": "dark"}],
                "placements": [{"item": "bed_default", "x": 30, "y": 30}],
                "storage": {"lamp": 2},
                "ground": "ground_1",
                "coord_scale": 2,
            },
            "house_draft": {
                "layout": {
                    "rooms": [{"x": 7, "y": 7, "w": 5, "h": 4, "floor": "brick"}],
                    "placements": [],
                    "storage": {},
                    "ground": "ground_2",
                    "coord_scale": 2,
                },
                "built_room_index": [0],
            },
            "house_blueprints": [
                {
                    "slot": 0,
                    "name": "Cozy",
                    "layout": {
                        "rooms": [{"x": 8, "y": 8, "w": 3, "h": 3, "floor": "dark"}],
                        "placements": [],
                        "storage": {},
                        "ground": "ground_1",
                        "coord_scale": 2,
                    },
                }
            ],
        },
        "pets": [],
        "questProgress": [],
        "farmingPatches": [{"patchNumber": 1, "cropType": "starfruit"}],
        "sessions": [
            {
                "session_id": "s1",
                "skill_name": "thieving",
                "activity_key": "bishop",
                "started_at": 1,
                "ends_at": 2,
                "frames": [],
                "completed": False,
                "is_worker_session": True,
                "worker_slot": 1,
                "efficiency_multiplier": 2.5,
            }
        ],
    }
    base.update(overrides)
    return base


class ParserTests(unittest.TestCase):
    def test_sig_is_known_and_not_an_unknown_field(self) -> None:
        raw = _save()
        issues = analyze_save(raw)
        self.assertFalse(any(i["code"] == "unknown_top_level" and i.get("field") == "sig" for i in issues))
        data = normalize_save(raw)
        self.assertTrue(data["meta"]["signed"])
        self.assertNotIn("sig", data["extensions"])

    def test_slayer_display_name_derived_from_enemy_key(self) -> None:
        data = normalize_save(_save())
        task = data["combat"]["slayer_task"]
        self.assertEqual(task["enemy_key"], "hellhound")
        self.assertEqual(task["display_name"], "Hellhound")
        self.assertEqual(data["combat"]["foretold_tasks"][0]["display_name"], "Goblin")

    def test_prestige_tower_workers_and_loadouts(self) -> None:
        data = normalize_save(_save())
        agility = next(s for s in data["skills"] if s["key"] == "agility")
        self.assertEqual(agility["prestige"], 3)
        self.assertEqual(data["tower"]["best_floor"], 86)
        self.assertEqual(data["workers"][0]["name"], "Ymir")
        self.assertEqual(data["loadouts"][0]["style"], "magic")
        self.assertEqual(data["character"]["title_name"], "Godslayer")
        self.assertEqual(data["character"]["notes"], "next: willow logs")
        self.assertTrue(data["sessions"][0]["is_worker"])
        self.assertEqual(data["farming"][0]["cropType"], "starfruit")

    def test_house_layout_draft_and_blueprints(self) -> None:
        data = normalize_save(_save())
        house = data["house"]
        self.assertIsNotNone(house)
        self.assertEqual(house["stats"]["room_count"], 1)
        self.assertEqual(house["ground"], "ground_1")
        self.assertEqual(house["placements"][0]["item"], "bed_default")
        self.assertEqual(house["placements"][0]["cell_x"], 15)
        self.assertEqual(house["storage"][0]["key"], "lamp")
        self.assertEqual(house["storage"][0]["qty"], 2)

        draft = data["house_draft"]
        self.assertIsNotNone(draft)
        self.assertEqual(draft["layout"]["rooms"][0]["floor"], "brick")
        self.assertEqual(draft["built_room_index"], [0])

        blueprints = data["house_blueprints"]
        self.assertEqual(len(blueprints), 1)
        self.assertEqual(blueprints[0]["name"], "Cozy")
        self.assertEqual(blueprints[0]["layout"]["stats"]["room_count"], 1)

    def test_combat_loadout(self) -> None:
        data = normalize_save(_save())
        loadout = data["combat"]["loadout"]
        self.assertTrue(loadout["has_data"])
        self.assertEqual(loadout["food_count"], 2)
        self.assertEqual(loadout["food_eat_threshold_pct"], 60)
        self.assertEqual(loadout["magic_spell"]["key"], "blood_wave")
        self.assertEqual(loadout["arrows"]["key"], "mithril_arrows")
        self.assertEqual(loadout["boss_coin_day_label"], "2026-07-14")
        self.assertEqual(len(loadout["boss_coin_kills"]), 2)
        self.assertTrue(loadout["boss_repeat"]["active"])
        self.assertEqual(loadout["boss_repeat"]["label"], "2/5")

    def test_prestige_talent_tree(self) -> None:
        data = normalize_save(_save())
        prestige = data["prestige"]
        self.assertEqual(prestige["player_race"], "human")
        agility = next(s for s in prestige["skills"] if s["key"] == "agility")
        self.assertEqual(agility["prestige_count"], 3)
        self.assertEqual(agility["points_earned"], 9)
        self.assertEqual(agility["points_spent"], 2)
        self.assertEqual(agility["points_unspent"], 7)
        endurance = next(p for p in agility["paths"] if p["key"] == "endurance")
        owned = next(n for n in endurance["nodes"] if n["id"] == "agility_endurance_1")
        self.assertTrue(owned["owned"])
        xp_path = next(p for p in agility["paths"] if p["key"] == "xp")
        self.assertTrue(xp_path["auto"])
        self.assertTrue(all(n["owned"] for n in xp_path["nodes"][:3]))
        self.assertTrue(any(e["effect"] == "xp_pct" for e in agility["effects"]))

    def test_legacy_save_without_new_fields_still_works(self) -> None:
        data = normalize_save({
            "exported_at": 1,
            "coins": 5,
            "skillLevels": {"mining": 2},
            "skillXp": {"mining": 10},
            "inventory": {"iron_ore": 1},
            "flags": {"character_name": "Old"},
        })
        self.assertEqual(data["character"]["name"], "Old")
        self.assertEqual(data["tower"]["best_floor"], 0)
        self.assertEqual(data["workers"], [])
        self.assertIsNone(data["house"])
        self.assertIsNone(data["house_draft"])
        self.assertEqual(data["house_blueprints"], [])
        self.assertEqual(data["prestige"]["skills"], [])
        self.assertFalse(data["meta"]["signed"])
        mining = data["skills"][0]
        self.assertEqual(mining["prestige"], 0)

    def test_new_item_categories(self) -> None:
        self.assertEqual(categorize_item("slayer_helm"), "Armor")
        self.assertEqual(categorize_item("mithril_pickaxe"), "Tools")
        self.assertEqual(categorize_item("staff_of_fire"), "Magic")
        self.assertEqual(categorize_item("archers_ring"), "Gems & Jewelry")
        self.assertEqual(categorize_item("magic_herb"), "Herbs")
        self.assertEqual(categorize_item("oak_bookshelf"), "Construction")
        self.assertEqual(categorize_item("mithril_axe"), "Tools")
        self.assertEqual(categorize_item("iron_battleaxe"), "Melee Weapons")

    def test_real_export_if_present(self) -> None:
        path = Path(__file__).parent / ".tmp" / "fantasyidler_save (20).json"
        if not path.is_file():
            self.skipTest("sample export not present")
        data, issues = parse_save_file(path)
        self.assertFalse(any(i["level"] == "error" for i in issues))
        self.assertFalse(any(i["code"] == "unknown_top_level" for i in issues))
        self.assertTrue(data["meta"]["signed"])
        self.assertGreater(data["tower"]["best_floor"], 0)
        self.assertTrue(any(s["prestige"] for s in data["skills"]))
        self.assertEqual(data["combat"]["slayer_task"]["display_name"], "Hellhound")
        self.assertGreaterEqual(len(data["workers"]), 1)
        self.assertGreaterEqual(len(data["loadouts"]), 1)
        cats = {i["category"] for i in data["inventory"]}
        self.assertIn("Tools", cats)
        self.assertIn("Herbs", cats)


if __name__ == "__main__":
    unittest.main()
