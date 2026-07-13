# Command Inventory

Audit date: 2026-07-12

## Setup Commands

- `/register_clan_role`
- `/register_special_role`
- `/register_special_channel`
- `/register_primary_clan`
- `/unregister_primary_clan`
- `/finish_setup`

## Member And Update Commands

- `/register`
- `/update`
- `/update_member`
- `/update_all_members`
- `/unregister_member`
- `/register_member`
- `/unregister_all_members`
- `/set_reminder_time`

## Status And Report Commands

- `/decks_report`
- `/medals_report`
- `/player_report`
- `/stats_report`
- `/stats`

## River Race Commands

- `/predict`
- `/river_race_status`

## Statistics Commands

- `/top_decks`
- `/suggest_war_decks`

## Leadership Utility Commands

- `/send_reminder`
- `/export`
- `/clan_kick`
- `/undo_kick`

## Strike Commands

- `/give_strike`
- `/remove_strike`
- `/strikes`

## Automation Commands

- `/set_automation_status`
- `/set_participation_requirements`
- `/check_automation_status`

## Context Menus

- `Update`
- `Give Strike`
- `Remove Strike`
- `Player Report`
- `Stats Report`

## Gaps Against Target Plan

- No `/me`, `/my_war_stats`, `/my_history`, `/war_status`, `/leaderboard`, or `/help` commands yet.
- No `/new_members`, `/probation_report`, `/missing_decks`, `/war_report`, `/review_candidates`, `/record_absence`, `/remove_absence`, `/suggested_strikes`, `/approve_strike`, `/waive_strike`, `/add_note`, `/membership_history`, `/sync_now`, or `/bot_health` commands yet.
- No `/configure_channels`, `/configure_roles`, `/configure_thresholds`, `/configure_schedules`, `/configure_permissions`, `/rebuild_aggregates`, `/retry_failed_sync`, or `/backup_status` commands yet.
- Existing strike commands mutate counts directly instead of creating auditable review events.
- Existing export command does not expose the target workbook variants.
