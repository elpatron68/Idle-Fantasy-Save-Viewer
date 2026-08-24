# Game data attribution

Recipe JSON files in `recipes/` are synced from the Idle Fantasy open-source game:

- **Source:** https://github.com/tristinbaker/IdleFantasy
- **Path:** `app/src/main/assets/data/recipes/`
- **License:** GNU General Public License v3.0

`house_tiles.json` is copied from `app/src/main/assets/data/house_tiles.json` under the same license.

`prestige_paths.json` is copied from `app/src/main/assets/data/prestige_paths.json` under the same license.

Refresh recipes with: `python scripts/sync_game_data.py`

The `manifest.json` file records the upstream git ref used for the last sync.
