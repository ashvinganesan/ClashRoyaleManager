# Scheduled Job Inventory

Audit date: 2026-07-12

All schedules are currently defined with `aiocron` inside `ClashRoyaleManager/cogs/automated_routines.py`. They are hard-coded UTC cron expressions.

| Schedule | Job | Current behavior |
| --- | --- | --- |
| `20-58 9 * * *` | `reset_time_check` | Detects daily reset, updates cards, cleans database, prepares battle days, records deck usage, and may update battle stats. |
| `59 9 * * *` | `final_reset_time_check` | Performs daily reset work if reset was not detected earlier. |
| `0 10 * * 0,2-6` | `end_of_day` | Remedies deck usage and resets in-memory reset tracking. |
| `0 10 * * 1` | `end_of_race_check` | Finalizes race data, updates stats, saves clan standings, creates new season when needed, prepares next River Race, and fixes anomalies. |
| `0,15,30,45 10-23 * * 4,5,6,0` | `evening_stats_checker` | Polls Battle Day stats during UTC daytime/evening windows. |
| `0,15,30,45 0-9 * * 5,6,0,1` | `morning_stats_checker` | Polls Battle Day stats during UTC overnight/morning windows. |
| `30 13 * * 4,5,6,0` | `automated_reminder_asia` | Sends ASIA reminder pings. |
| `0 19 * * 4,5,6,0` | `automated_reminder_eu` | Sends EU reminder pings. |
| `0 3 * * 5,6,0,1` | `automated_reminder_na` | Sends NA reminder pings. |
| `30 7,15,23 * * *` | `update_all_members` | Updates Discord roles and nicknames for all guild members. |
| `0 10 * * 0` | `check_early_completion_status` | Checks whether clans completed early. |
| `0 14 * * 1` | `assign_strikes` | Determines River Race failures and directly increments strike counts for active members when enabled. |

## Risks

- Job schedules are code constants, not configuration.
- Job executions are not persisted in a `sync_runs` or `job_runs` table.
- Failures are logged but not surfaced through health state or admin alerts.
- Battle-log polling is coupled to medal increases, so missed API windows need special review.
- Direct Monday strike mutation must be replaced by suggested strike events before production.
- In-memory reset tracking is lost on process restart.
