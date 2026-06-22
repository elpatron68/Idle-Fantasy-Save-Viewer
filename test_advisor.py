"""Tests for skill training advisor."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from advisor import advise_skill, crafts_to_next_level, missing_materials
from game_data import recipes_for_skill, xp_per_minute
from parser import load_save, normalize_save


class AdvisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.save_path = Path(__file__).parent / "testfiles" / "fantasyidler_save-3.json"
        if not cls.save_path.is_file():
            raise unittest.SkipTest("test save not available")
        raw, _ = load_save(cls.save_path)
        cls.snapshot = normalize_save(raw, source_file=str(cls.save_path))

    def test_recipes_loaded(self) -> None:
        recipes = recipes_for_skill("smithing")
        self.assertIn("iron_bar", recipes)
        self.assertAlmostEqual(xp_per_minute(recipes["iron_bar"]), 12.5)

    def test_missing_materials(self) -> None:
        missing = missing_materials({"iron_ore": 5}, {"iron_ore": 2})
        self.assertEqual(missing, {"iron_ore": 3})

    def test_smithing_advisor_level_57(self) -> None:
        result = advise_skill("smithing", self.snapshot, limit=5)
        self.assertTrue(result["supported"])
        self.assertEqual(result["skill_level"], 57)
        recs = result["recommendations"]
        self.assertGreater(len(recs), 0)
        self.assertEqual(recs[0]["activity_key"], "steel_platebody")
        self.assertEqual(recs[0]["xp_per_minute"], 187.5)

    def test_crafts_to_next_level(self) -> None:
        self.assertEqual(crafts_to_next_level(100, 12.5), 8)
        self.assertEqual(crafts_to_next_level(0, 12.5), 0)
        self.assertEqual(crafts_to_next_level(10, 0), 0)

    def test_item_goal_from_recipe_not_in_inventory(self) -> None:
        from db import create_goal, get_connection, import_save, init_db

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "goal.db"
            import_save(self.save_path, db_path=db)
            conn = get_connection(db)
            init_db(conn)
            conn.close()
            goal = create_goal("steel_platebody", 5, mode="relative", db_path=db)
            self.assertEqual(goal["item_key"], "steel_platebody")
            self.assertEqual(goal["mode"], "relative")
            self.assertEqual(goal["target_qty"], 5)

    def test_unsupported_skill(self) -> None:
        result = advise_skill("combat", self.snapshot)
        self.assertFalse(result.get("supported"))


if __name__ == "__main__":
    unittest.main()
