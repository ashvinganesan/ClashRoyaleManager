# Baseline Audit

Source baseline: `chris-janzen/ClashRoyaleManager`
Fork: `ashvinganesan/ClashRoyaleManager`
Baseline commit: `32b6edab5c74dfc0391b7212015c44395f3afd97`
Local branch: `phase-0-baseline`
Audit date: 2026-07-12

## Executive Summary

The upstream project is a useful starting point, not a production-ready deployment for our clan. It already includes Discord slash commands, role and nickname management, River Race tracking, reminders, strike assignment, prediction, Excel exports, and MySQL persistence. The current implementation is tightly coupled and relies on hard-coded Python credentials, direct synchronous HTTP calls, manual SQL schema setup, and automation that can mutate strike counts without an approval workflow.

The first implementation goal is to preserve the valuable behavior while adding reproducibility, tests, secret handling, data-quality safeguards, and human-review moderation controls.

## Repository Layout

- `ClashRoyaleManager/__main__.py` creates the Discord bot, switches between setup commands and normal commands, syncs commands to one guild, initializes cached roles/channels, and starts automated routines after setup.
- `ClashRoyaleManager/commands/` contains slash commands and context menus.
- `ClashRoyaleManager/cogs/automated_routines.py` contains scheduled jobs using `aiocron`.
- `ClashRoyaleManager/utils/clash_utils.py` contains Clash Royale API calls and response interpretation.
- `ClashRoyaleManager/utils/db_utils.py` contains database access, membership updates, River Race persistence, strike mutation, kick logging, card downloads, and Excel exports.
- `ClashRoyaleManager/utils/stat_utils.py` contains stat aggregation, strike determination, and race prediction calculations.
- `db_schema.sql` contains the current full schema.
- `db_updates/` contains manual schema update scripts, but there is no migration runner.
- `requirements.txt` pins runtime dependencies.

## Existing Capabilities To Preserve

- Discord registration and manual admin registration.
- Discord role and nickname synchronization.
- Multi-clan configuration.
- River Race deck-use tracking.
- Battle-log-based win/loss tracking.
- Unused-deck reminders.
- Manual strike add/remove commands.
- Existing export command and workbook generation.
- River Race prediction commands.
- Kick logging from command flow and screenshot listener.

## Current Schema

The current schema includes `users`, `clans`, `primary_clans`, `clan_affiliations`, `clan_time`, `river_races`, `river_race_clans`, `river_race_user_data`, `pvp_battles`, `duels`, `boat_battles`, `cards`, `decks`, `deck_cards`, `kicks`, role/channel mapping tables, `seasons`, and `variables`.

The schema already has useful history primitives, especially player tags, clan affiliations, clan time ranges, River Race records, daily deck fields, battle tables, and kicks. It does not yet have explicit sync audit records, raw API snapshots, data-completeness status, probation, excused absence records, leadership notes, auditable strike events, export records, or configuration audit records.

## Configuration And Secrets

Upstream baseline behavior:

- `ClashRoyaleManager/__main__.py` imports `BOT_TOKEN` from `config.credentials`.
- `utils/clash_utils.py` imports `CLASH_API_KEY` from `config.credentials`.
- `utils/db_utils.py` imports `IP`, `USERNAME`, `PASSWORD`, and `DATABASE_NAME` from `config.credentials`.
- README instructs the operator to create `ClashRoyaleManager/config/credentials.py`.

Initial remediation in this branch:

- Added environment-variable configuration in `ClashRoyaleManager/config/settings.py`.
- Added `.env.example`.
- Kept `.env`, `.env.*`, and `credentials.py` ignored.
- Updated token/API/database callers to use env-backed settings.

Remaining work:

- Validate all missing configuration on startup before Discord connects.
- Redact secrets from logs.

## Dependencies

Current pinned dependencies:

- `aiocron==1.4`
- `discord.py==2.0.1`
- `numpy==1.21.5`
- `opencv_python==4.5.4.60`
- `prettytable==2.1.0`
- `PyMySQL==1.0.2`
- `pytesseract==0.3.8`
- `requests==2.22.0`
- `setuptools==45.2.0`
- `XlsxWriter==3.0.1`

Risks:

- `discord.py==2.0.1` is old for a long-running Discord bot.
- `requests==2.22.0` is old and should not remain pinned for production.
- `numpy==1.21.5` limits supported Python versions.
- Synchronous `requests` calls run inside async command and scheduled-job flows.
- There is no lockfile, no Python version declaration, and no CI.

## Clash Royale API Usage

Observed endpoints:

- `GET /v1/cards`
- `GET /v1/players/{playerTag}`
- `GET /v1/players/{playerTag}/battlelog`
- `GET /v1/clans/{clanTag}`
- `GET /v1/clans/{clanTag}/members`
- `GET /v1/clans/{clanTag}/currentriverrace`
- `GET /v1/clans/{clanTag}/riverracelog?limit=1`

Risks:

- Requests have no explicit timeout.
- Retry and rate-limit behavior is not centralized.
- API failures can be caught and skipped in some routines, but there is no persistent sync audit trail.
- Raw snapshots are not retained.
- Missing data is not modeled as a first-class status.

## Automation Risks

Automated jobs are hard-coded in UTC cron strings inside `AutomatedRoutines.__init__`. They cover reset detection, end-of-day processing, end-of-race processing, battle-log polling, reminders, member updates, early completion checks, and Monday strike assignment.

The highest-risk behavior is Monday automated strike assignment: `assign_strikes` calls `db_utils.update_strikes(player_tag, 1)` for active members. The project plan allows suggested strikes, but production should require a review workflow before final strike counts are changed.

## Initial Implementation Priorities

1. Add reproducible local development and deployment scaffolding.
2. Replace Python-file secrets with environment variables.
3. Add tests around tag normalization, stat calculations, strike determination, and export structure before behavior changes.
4. Add migration tooling around the existing schema.
5. Add sync audit/data-completeness primitives before changing moderation logic.
6. Convert automatic strike assignment into suggested strike events with manual approval.
7. Expand exports after data contracts and tests are in place.
