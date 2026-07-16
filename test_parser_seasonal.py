"""Tests for seasonal / tower / carnival save parsing."""

from __future__ import annotations

import unittest
from pathlib import Path

from parser import load_save, normalize_save


class SeasonalParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.save_path = Path(__file__).parent / ".tmp" / "fantasyidler_save.json"
        if not cls.save_path.is_file():
            cls.save_path = Path(__file__).parent / "testfiles" / "fantasyidler_save-3.json"
        if not cls.save_path.is_file():
            raise unittest.SkipTest("test save not available")
        raw, _ = load_save(cls.save_path)
        cls.snapshot = normalize_save(raw, source_file=str(cls.save_path))

    def test_seasonal_event(self) -> None:
        seasonal = self.snapshot["seasonal"]
        self.assertIn("tokens_by_event", seasonal)
        self.assertIn("active_event_id", seasonal)
        self.assertIn("bounty_slots", seasonal)
        if seasonal.get("active_event_id"):
            event_id = seasonal["active_event_id"]
            self.assertIsInstance(seasonal["bounty_slots"], list)

    def test_tower(self) -> None:
        tower = self.snapshot["tower"]
        self.assertIn("current_floor", tower)
        self.assertIn("best_floor", tower)
        self.assertIn("milestones", tower)

    def test_carnival_cooldowns(self) -> None:
        carnival = self.snapshot["carnival"]
        self.assertIn("cooldowns", carnival)
        self.assertIn("ring_toss", carnival["cooldowns"])

    def test_workers(self) -> None:
        workers = self.snapshot["workers"]
        self.assertIsInstance(workers, list)

    def test_titles(self) -> None:
        titles = self.snapshot["titles"]
        self.assertIn("unlocked", titles)
        self.assertIn("equipped", titles)

    def test_expeditions(self) -> None:
        expeditions = self.snapshot["expeditions"]
        self.assertIn("unlocked", expeditions)
        self.assertIn("notes", expeditions)
        self.assertIn("pity", expeditions)

    def test_dungeon_stats(self) -> None:
        stats = self.snapshot["dungeon_stats"]
        self.assertIsInstance(stats, dict)
        for entry in stats.values():
            self.assertIn("food_consumed", entry)
            self.assertIn("kill_count", entry)
            self.assertIn("survived", entry)

    def test_sunspire_save_values(self) -> None:
        if self.snapshot["seasonal"].get("active_event_id") != "sunspire_solstice_2026":
            self.skipTest("not sunspire save")
        self.assertEqual(
            self.snapshot["seasonal"]["tokens_by_event"]["sunspire_solstice_2026"],
            31,
        )
        self.assertEqual(len(self.snapshot["seasonal"]["bounty_slots"]), 3)
        self.assertEqual(self.snapshot["tower"]["current_floor"], 39)
        self.assertEqual(self.snapshot["workers"][0]["daily_name"], "Dwyn")
        self.assertIn("master_angler", self.snapshot["titles"]["unlocked"])


if __name__ == "__main__":
    unittest.main()
