# Changelog

All notable changes to the Idle Fantasy Save Viewer are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2026-09-26]

Save Viewer update for newer Idle Fantasy exports (v1.14.8+ flags), plus CI/deploy fixes and documentation.

### Added

- **Combat loadout (Paket 1):** Boss/dungeon repeat snapshots, food eat order, shop XP boost expiry in parser and UI.
- **Farming & guild (Paket 2):** Farming meta (magic bean, fertilizer, last crops), monument touch day, prayer pity, guild daily tier counts and quest reset levels.
- **Elder Isle & heirlooms (Paket 3):** Elder Isle progress (skills, craft queue, sigils, quests), heirloom mirror sessions in overview.
- **Quests & skills (Paket 4):** Quest reset hour and next reset times on daily/weekly/guild tabs; Elder Isle skills table on Skills tab; blessing expiry and last XP boost purchase on overview.
- **Character & events (Paket 5):** Character creation time, shop “keep one of each”, in-game auto-backup summary (no folder URI), structured carnival difficulties and last tab.
- **Feintuning:** In-game UI preferences (theme, compact numbers, font scale); compact number formatting in the viewer when enabled in the save; Elder main quests listed by name; `heirlooms.json` rebuilt from upstream `equipment.json` via `scripts/sync_game_data.py`.
- **CHANGELOG.md** (this file).

### Changed

- **README:** Extended feature list and “Overview (extended save fields)” section; sync docs include heirlooms.
- **Upstream sync workflow:** Resolve `main` via `git ls-remote` instead of GitHub REST API to avoid rate limits (403).

### Fixed

- **Deploy CI:** Install dependencies before `import app` smoke test (continues to run parser/advisor tests on deploy).

## [2026-09-02]

### Added

- v1.14.8 overview features: heirlooms, hired mercenaries, seasonal extras, queue duration, locked items, bulk-sell receipts.

### Fixed

- **Docker:** Include `heirloom_data.py` in image (502 on production).
- **Deploy CI:** `pip install` before application smoke test.

## [2026-08-24]

Earlier releases: house tab, prestige, combat loadout foundations, inventory categories, README/screenshots, Plausible URL redaction. See git history and merged PRs #3–#7.

[2026-09-26]: https://github.com/elpatron68/Idle-Fantasy-Save-Viewer/compare/0e7309b...720f057
