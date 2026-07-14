"""Tiny Discord bot entry point."""

import asyncio
import datetime as dt
import logging
import re
import secrets
import string
from pathlib import Path
from typing import Any, Optional

import discord
from discord import app_commands

from microbot.clash_api import ClashApiError, ClashClient, ClashNotFound
from microbot.config import Settings, load_settings, normalize_tag
from microbot.storage import Store


LOG = logging.getLogger("microbot")
DEFAULT_VERIFICATION_CHANNEL_NAME = "verification-confirmation"
DEFAULT_KICK_THRESHOLD = 2000
DEFAULT_PROMOTION_THRESHOLD = 2500
CONFIRM_VERIFICATION_ROLE_NAMES = {"elder"}
DEFAULT_ELDER_ROLE_NAMES = {"elder"}
DEFAULT_COLEADER_ROLE_NAMES = {"co-leader", "co leader", "coleader"}
MIN_LEADERBOARD_WARS = 2
MIN_LEADERBOARD_DAYS = 14
MIN_PROMOTION_WARS = 3
RIVER_RACE_LOG_LIMIT = 10
ROLLING_WAR_DAYS = 35
LAST_WAR_BOTTOM_START_RANK = 41
DISCORD_MENTION_RE = re.compile(r"^<@!?(\d+)>$")
PLAYER_TAG_CHARACTERS = set("0289PYLQGRJCUV")
JOIN_DATE_BASELINE_DATE = dt.date(2026, 5, 4)
JOIN_DATE_BASELINE_SETTING = "join_date_baseline_completed"
JOIN_DATE_BASELINE_SOURCE = "auto-baseline"
JOIN_DATE_TRACKED_SOURCE = "auto-roster"
JOIN_DATE_SYNC_INTERVAL_SECONDS = 7 * 24 * 60 * 60
FULL_WAR_JOIN_CUTOFF_BEFORE_END = dt.timedelta(days=4)
FIRST_OBSERVED_FULL_WAR_FAME_FLOOR = 2000
MIN_KICK_DEMOTION_SAMPLE_WARS = 3
RIVER_RACE_LOG_SOURCE = "river race log"
ROLE_MARKERS = {
    "member": "🟫 Member",
    "elder": "🟩 Elder",
    "coleader": "🟥 Co-leader",
    "leader": "🟥 Leader",
}


def discord_name(user: Any) -> str:
    """Return a stable display name for logs/storage."""
    discriminator = getattr(user, "discriminator", "0")
    return user.name if discriminator == "0" else f"{user.name}#{discriminator}"


def make_code() -> str:
    """Create a short verification code."""
    alphabet = string.ascii_uppercase + string.digits
    return "CR-" + "".join(secrets.choice(alphabet) for _ in range(6))


def player_clan(player: dict) -> tuple[Optional[str], Optional[str]]:
    """Extract clan tag/name from a player payload."""
    clan = player.get("clan") or {}
    return clan.get("tag"), clan.get("name")


def int_value(value: Any) -> int:
    """Return an integer for numeric API values."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def clip_text(value: str, limit: int = 1024) -> str:
    """Keep embed field text within Discord's limit."""
    if len(value) <= limit:
        return value

    return value[: limit - 3].rstrip() + "..."


def format_name(value: Any) -> str:
    """Escape player/clan names for Discord embeds."""
    return discord.utils.escape_markdown(str(value or "Unknown"))


def parse_clash_time(value: Optional[str]) -> Optional[dt.datetime]:
    """Parse Clash Royale API timestamps."""
    if not value:
        return None

    for time_format in ("%Y%m%dT%H%M%S.%fZ", "%Y%m%dT%H%M%SZ"):
        try:
            return dt.datetime.strptime(value, time_format).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue

    return None


def parse_iso_datetime(value: Optional[str]) -> Optional[dt.datetime]:
    """Parse an ISO timestamp from SQLite."""
    if not value:
        return None

    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_join_date_argument(value: str) -> Optional[dt.datetime]:
    """Parse a manual join date in YYYY-MM-DD format."""
    try:
        parsed_date = dt.date.fromisoformat(value.strip())
    except ValueError:
        return None

    return dt.datetime.combine(parsed_date, dt.time.min, tzinfo=dt.timezone.utc)


def presence_value(presence: Optional[Any], key: str) -> Optional[str]:
    """Read a field from a SQLite row or test dict."""
    if presence is None:
        return None

    try:
        return presence[key]
    except (KeyError, IndexError):
        return None


def row_to_dict(row: Any) -> dict:
    """Convert a SQLite row or mapping to a plain dict."""
    if row is None:
        return {}

    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}

    return dict(row)


def merge_join_dates(presence_map: dict, join_date_map: dict) -> dict:
    """Merge manually known join dates into the presence map."""
    merged = {tag: row_to_dict(presence) for tag, presence in presence_map.items()}

    for player_tag, join_row in join_date_map.items():
        target = merged.setdefault(player_tag, {})
        target["manual_joined_at"] = join_row["joined_at"]
        target["manual_join_source"] = join_row["source"]
        target["manual_join_updated_at"] = join_row["updated_at"]

    return merged


def known_join_date(presence: Optional[Any]) -> Optional[dt.datetime]:
    """Return a manually known join date when one is configured."""
    return parse_iso_datetime(presence_value(presence, "manual_joined_at"))


def membership_context_date(presence: Optional[Any], first_seen_at: Optional[dt.datetime]) -> tuple[Optional[dt.datetime], str]:
    """Return the best membership date and label for display."""
    joined_at = known_join_date(presence)

    if joined_at is not None:
        return joined_at, "joined"

    return first_seen_at, "seen"


def membership_context_text(value: Optional[dt.datetime], label: str, now: dt.datetime) -> str:
    """Format a membership date for compact war rows."""
    return f"{label} {short_date(value)} ({days_ago_label(value, now)})"


def short_date(value: Optional[dt.datetime]) -> str:
    """Format a short UTC date."""
    if value is None:
        return "unknown"

    return value.astimezone(dt.timezone.utc).strftime("%b %-d")


def days_ago_label(value: Optional[dt.datetime], now: dt.datetime) -> str:
    """Return a compact age label."""
    if value is None:
        return "unknown"

    days = age_days(value, now) or 0

    if days == 0:
        return "today"

    if days == 1:
        return "1 day"

    return f"{days} days"


def age_days(value: Optional[dt.datetime], now: dt.datetime) -> Optional[int]:
    """Return age in UTC calendar days."""
    if value is None:
        return None

    return max(0, (now.date() - value.astimezone(dt.timezone.utc).date()).days)


def has_min_tenure(value: Optional[dt.datetime], now: dt.datetime, min_days: int) -> bool:
    """Return whether a first-seen timestamp is at least the given age."""
    days = age_days(value, now)
    return days is not None and days >= min_days


def race_clan_from_log_item(log_item: dict, clan_tag: Optional[str]) -> Optional[dict]:
    """Return this clan's standing entry from a river race log item."""
    standings = log_item.get("standings") or []

    for standing in standings:
        standing_clan = standing.get("clan") or {}

        if not clan_tag or standing_clan.get("tag") == clan_tag:
            return standing_clan

    return None


def can_be_promoted(member: dict) -> bool:
    """Return whether a clan member can still receive an in-game promotion."""
    return normalized_role(member) not in {"coleader", "leader"}


def normalized_role(member: dict) -> str:
    """Return a normalized Clash Royale clan role key."""
    return str(member.get("role") or "member").replace("_", "").replace("-", "").lower()


def player_role_key(player: dict) -> Optional[str]:
    """Return a normalized role from a player payload when the API includes one."""
    if player.get("role"):
        return normalized_role(player)

    clan = player.get("clan") or {}

    if clan.get("role"):
        return normalized_role(clan)

    return None


def role_label(member: dict) -> str:
    """Return a compact, colored role marker for Discord war rows."""
    return ROLE_MARKERS.get(normalized_role(member), f"⬜ {format_name(member.get('role') or 'Unknown')}")


def has_named_role(user: Any, role_names: set[str]) -> bool:
    """Return whether a Discord user/member has one of the named roles."""
    for role in getattr(user, "roles", []) or []:
        if str(getattr(role, "name", "")).casefold() in role_names:
            return True

    return False


def can_confirm_verification_user(user: Any) -> bool:
    """Return whether a Discord user/member can confirm verifications."""
    permissions = getattr(user, "guild_permissions", None)

    if getattr(permissions, "administrator", False):
        return True

    return has_named_role(user, CONFIRM_VERIFICATION_ROLE_NAMES)


def can_confirm_verification(interaction: discord.Interaction) -> bool:
    """App command check for verification confirmation."""
    return can_confirm_verification_user(interaction.user)


def discord_id_from_mention(value: str) -> Optional[int]:
    """Extract a Discord user id from a mention string."""
    match = DISCORD_MENTION_RE.fullmatch(value.strip())

    if not match:
        return None

    return int(match.group(1))


def is_likely_player_tag(value: str) -> bool:
    """Return whether a query looks like a Clash Royale player tag."""
    cleaned = value.strip().upper().replace("O", "0")

    if cleaned.startswith("#"):
        cleaned = cleaned[1:]

    return bool(cleaned) and all(character in PLAYER_TAG_CHARACTERS for character in cleaned)


async def send_ephemeral(interaction: discord.Interaction, message: str):
    """Send an ephemeral command response or followup."""
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def build_war_stats_embed(race: dict, members_payload: dict) -> discord.Embed:
    """Build a current river race status embed."""
    clan = race.get("clan") or {}
    race_clans = race.get("clans") or []
    participants = clan.get("participants") or []
    members = members_payload.get("items") or []
    participants_by_tag = {participant.get("tag"): participant for participant in participants}

    fame = sum(int_value(participant.get("fame")) for participant in participants)
    decks_today = sum(int_value(participant.get("decksUsedToday")) for participant in participants)
    decks_total = sum(int_value(participant.get("decksUsed")) for participant in participants)
    member_count = len(members)
    roster_capacity = member_count * 4

    remaining_roster_decks = 0
    no_decks_today = 0
    needs_decks = []

    for member in members:
        participant = participants_by_tag.get(member.get("tag"), {})
        member_decks_today = min(4, int_value(participant.get("decksUsedToday")))

        if member_decks_today == 0:
            no_decks_today += 1

        if member_decks_today < 4:
            remaining_roster_decks += 4 - member_decks_today
            needs_decks.append((member_decks_today, member.get("name"), member.get("tag")))

    title = f"{clan.get('name', 'Clan')} War Stats"
    embed = discord.Embed(
        title=title,
        description=f"Current river race for `{clan.get('tag', 'unknown')}`",
        color=discord.Color.blue(),
        timestamp=dt.datetime.now(dt.timezone.utc),
    )

    period_type = race.get("periodType", "unknown")
    period_index = int_value(race.get("periodIndex")) + 1
    decks_label = "training decks used" if is_training_period(race) else "decks used"
    embed.add_field(
        name="Summary",
        value=(
            f"Fame: **{fame:,}**\n"
            f"Decks today: **{decks_today}/200 {decks_label}**\n"
            f"Current roster remaining: **{remaining_roster_decks}/{roster_capacity}**\n"
            f"Decks total this race: **{decks_total} {decks_label}**\n"
            f"Members with 0 decks today: **{no_decks_today}**\n"
            f"Period: **{format_name(period_type)} {period_index}**"
        ),
        inline=False,
    )

    top_participants = sorted(
        participants,
        key=lambda participant: (
            int_value(participant.get("fame")),
            int_value(participant.get("decksUsed")),
            int_value(participant.get("decksUsedToday")),
        ),
        reverse=True,
    )[:10]
    top_lines = []

    for index, participant in enumerate(top_participants, 1):
        top_lines.append(
            f"{index}. {format_name(participant.get('name'))} - "
            f"{int_value(participant.get('fame')):,} fame, "
            f"{int_value(participant.get('decksUsedToday'))}/4 {decks_label} today"
        )

    embed.add_field(
        name="Top Contributors",
        value=clip_text("\n".join(top_lines) or "No war battles logged yet."),
        inline=False,
    )

    needs_decks.sort(key=lambda item: (item[0], str(item[1]).lower()))
    needs_decks_lines = [
        f"{format_name(name)} - {used}/4 {decks_label}"
        for used, name, _ in needs_decks[:12]
    ]

    if len(needs_decks) > 12:
        needs_decks_lines.append(f"...and {len(needs_decks) - 12} more")

    embed.add_field(
        name="Still Has Decks Today",
        value=clip_text("\n".join(needs_decks_lines) or "Everyone on the current roster is at 4/4."),
        inline=False,
    )

    standings = sorted(race_clans, key=lambda item: int_value(item.get("fame")), reverse=True)
    standings_lines = []

    for index, race_clan in enumerate(standings, 1):
        clan_participants = race_clan.get("participants") or []
        clan_decks_today = sum(int_value(participant.get("decksUsedToday")) for participant in clan_participants)
        standings_lines.append(
            f"{index}. {format_name(race_clan.get('name'))} - "
            f"{int_value(race_clan.get('fame')):,} fame, {clan_decks_today} {decks_label} today"
        )

    embed.add_field(
        name="Race Standings",
        value=clip_text("\n".join(standings_lines) or "No race standings available."),
        inline=False,
    )
    embed.set_footer(text="Data from the Clash Royale API")
    return embed


def collect_completed_war_stats(race_log: dict,
                                clan_tag: Optional[str],
                                cutoff: dt.datetime) -> tuple[dict[str, dict], list[dt.datetime]]:
    """Collect rolling completed-war stats from the river race log."""
    player_stats: dict[str, dict] = {}
    race_dates = []

    for log_item in race_log.get("items") or []:
        completed_at = parse_clash_time(log_item.get("createdDate"))

        if completed_at is None or completed_at < cutoff:
            continue

        standing_clan = race_clan_from_log_item(log_item, clan_tag)

        if not standing_clan:
            continue

        race_dates.append(completed_at)

        for participant in standing_clan.get("participants") or []:
            player_tag = participant.get("tag")

            if not player_tag:
                continue

            entry = player_stats.setdefault(
                player_tag,
                {"name": participant.get("name", "Unknown"), "scores": [], "entries": []},
            )
            fame = int_value(participant.get("fame"))
            entry["name"] = participant.get("name", entry["name"])
            entry["scores"].append(fame)
            entry["entries"].append({"date": completed_at, "fame": fame})

    return player_stats, race_dates


def latest_completed_clan_race(race_log: dict,
                               clan_tag: Optional[str],
                               cutoff: dt.datetime) -> tuple[Optional[dt.datetime], Optional[dict]]:
    """Return the newest completed race log entry for this clan."""
    latest_at = None
    latest_clan = None

    for log_item in race_log.get("items") or []:
        completed_at = parse_clash_time(log_item.get("createdDate"))

        if completed_at is None or completed_at < cutoff:
            continue

        standing_clan = race_clan_from_log_item(log_item, clan_tag)

        if not standing_clan:
            continue

        if latest_at is None or completed_at > latest_at:
            latest_at = completed_at
            latest_clan = standing_clan

    return latest_at, latest_clan


def is_training_period(race: dict) -> bool:
    """Return whether the current river race period is training days."""
    return str(race.get("periodType") or "").lower() == "training"


def same_utc_day(first: dt.datetime, second: dt.datetime) -> bool:
    """Return whether two timestamps fall on the same UTC day."""
    return first.astimezone(dt.timezone.utc).date() == second.astimezone(dt.timezone.utc).date()


def is_full_completed_war(completed_at: dt.datetime,
                          first_seen_at: Optional[dt.datetime],
                          first_seen_source: Optional[str] = None,
                          fame: Optional[int] = None) -> bool:
    """Return whether a completed war should count for a member's average."""
    if first_seen_at is None:
        return True

    # Clash exposes race log completion times, not join timestamps or battle-day
    # boundaries. War battles end near the log timestamp; battle day 1 starts
    # roughly four days earlier, so members seen by then had battle day 1
    # available.
    if first_seen_at <= completed_at - FULL_WAR_JOIN_CUTOFF_BEFORE_END:
        return True

    # If the bot first saw a member from the river-race log itself, that
    # timestamp means "observed in this completed race", not "joined today".
    # A high first-observed score is strong evidence they had a real war week.
    return (
        first_seen_source == RIVER_RACE_LOG_SOURCE
        and fame is not None
        and fame >= FIRST_OBSERVED_FULL_WAR_FAME_FLOOR
        and same_utc_day(first_seen_at, completed_at)
    )


def eligible_completed_entries(history: dict,
                               first_seen_at: Optional[dt.datetime],
                               first_seen_source: Optional[str] = None) -> list[dict]:
    """Return completed war entries that should count for the member."""
    return [
        entry
        for entry in history.get("entries", [])
        if is_full_completed_war(entry["date"], first_seen_at, first_seen_source, entry["fame"])
    ]


def average_entry_fame(entries: list[dict]) -> Optional[float]:
    """Return average fame for completed war entries."""
    return (sum(entry["fame"] for entry in entries) / len(entries)) if entries else None


def has_short_history_good_war(full_entries: list[dict], kick_threshold: int) -> bool:
    """Return whether a short sample has at least one good full war."""
    return (
        0 < len(full_entries) < MIN_KICK_DEMOTION_SAMPLE_WARS
        and any(entry["fame"] >= kick_threshold for entry in full_entries)
    )


def should_suggest_kick_demotion(active_fame: Optional[int],
                                 average_fame: Optional[float],
                                 full_entries: list[dict],
                                 kick_threshold: int) -> bool:
    """Return whether a player belongs on the kick/demotion suggestion list."""
    if active_fame is None or active_fame >= kick_threshold:
        return False

    if average_fame is None:
        return True

    if average_fame >= kick_threshold:
        return False

    return not has_short_history_good_war(full_entries, kick_threshold)


def completed_war_score(history: dict, completed_at: Optional[dt.datetime]) -> int:
    """Return a player's score from a specific completed war."""
    if completed_at is None:
        return 0

    for entry in history.get("entries", []):
        if entry["date"] == completed_at:
            return entry["fame"]

    return 0


def active_score(current_fame: int,
                 history: dict,
                 active_completed_at: Optional[dt.datetime],
                 first_seen_at: Optional[dt.datetime],
                 first_seen_source: Optional[str] = None) -> tuple[Optional[int], str]:
    """Return the score to use for current report recommendations."""
    if active_completed_at is None:
        return current_fame, "current"

    completed_score = completed_war_score(history, active_completed_at)

    if not is_full_completed_war(active_completed_at, first_seen_at, first_seen_source, completed_score):
        return None, "last full war"

    return completed_score, "last war"


def estimate_current_race_start(race: dict, race_log: dict, now: dt.datetime) -> dt.datetime:
    """Estimate current race start because the API does not expose member join dates."""
    completed_dates = [
        parsed
        for parsed in (parse_clash_time(item.get("createdDate")) for item in race_log.get("items") or [])
        if parsed is not None
    ]

    if completed_dates:
        return max(completed_dates)

    period_index = int_value(race.get("periodIndex"))
    current_week_day = period_index % 7
    return now - dt.timedelta(days=current_week_day)


def record_war_presence(store: Store,
                        clan_tag: Optional[str],
                        race: dict,
                        members_payload: dict,
                        race_log: dict,
                        now: dt.datetime):
    """Record current and historical member sightings."""
    for member in members_payload.get("items") or []:
        if member.get("tag"):
            store.upsert_member_presence(
                member["tag"],
                member.get("name", "Unknown"),
                clan_tag,
                now,
                "current roster",
            )

    current_clan = race.get("clan") or {}

    for participant in current_clan.get("participants") or []:
        if participant.get("tag"):
            store.upsert_member_presence(
                participant["tag"],
                participant.get("name", "Unknown"),
                clan_tag,
                now,
                "current river race",
            )

    for log_item in race_log.get("items") or []:
        completed_at = parse_clash_time(log_item.get("createdDate"))

        if completed_at is None:
            continue

        standing_clan = race_clan_from_log_item(log_item, clan_tag)

        if not standing_clan:
            continue

        for participant in standing_clan.get("participants") or []:
            if participant.get("tag"):
                store.upsert_member_presence(
                    participant["tag"],
                    participant.get("name", "Unknown"),
                    clan_tag,
                    completed_at,
                    "river race log",
                )


def refresh_war_presence(store: Store,
                         clan_tag: Optional[str],
                         race: dict,
                         members_payload: dict,
                         race_log: dict,
                         now: dt.datetime) -> dict:
    """Refresh member presence and return the stored presence map."""
    record_war_presence(store, clan_tag, race, members_payload, race_log, now)
    return merge_join_dates(store.get_member_presence_map(), store.get_member_join_date_map())


def sync_roster_join_dates(store: Store,
                           clash: ClashClient,
                           clan_tag: Optional[str],
                           now: dt.datetime) -> tuple[int, dt.datetime, str]:
    """Seed missing known join dates from the current clan roster."""
    if not clan_tag:
        return 0, now, JOIN_DATE_TRACKED_SOURCE

    members_payload = clash.get_clan_members(clan_tag)
    members = members_payload.get("items") or []
    baseline_completed = store.get_setting(JOIN_DATE_BASELINE_SETTING) == "1"

    if baseline_completed:
        joined_at = now
        source = JOIN_DATE_TRACKED_SOURCE
    else:
        joined_at = dt.datetime.combine(JOIN_DATE_BASELINE_DATE, dt.time.min, tzinfo=dt.timezone.utc)
        source = JOIN_DATE_BASELINE_SOURCE

    inserted = store.seed_missing_member_join_dates(members, joined_at, source)

    if not baseline_completed:
        store.set_setting(JOIN_DATE_BASELINE_SETTING, "1")

    return inserted, joined_at, source


def score_line(role_text: str,
               name: str,
               active_fame: Optional[int],
               active_label: str,
               average_fame: Optional[float],
               race_count: int,
               membership_at: Optional[dt.datetime],
               membership_label: str,
               now: dt.datetime,
               reason: str) -> str:
    """Format a compact member war score line."""
    active_text = f"{active_fame:,}" if active_fame is not None else "n/a"
    average_text = f"{average_fame:,.0f}" if average_fame is not None else "n/a"
    return (
        f"{role_text} {format_name(name)} - {active_text} {active_label}, "
        f"{average_text} avg/{race_count} full wars, "
        f"{membership_context_text(membership_at, membership_label, now)}: {reason}"
    )


def fame_text(value: Optional[int]) -> str:
    """Format a fame value that can be unavailable."""
    return f"{value:,}" if value is not None else "n/a"


def average_fame_text(value: Optional[float]) -> str:
    """Format an average fame value."""
    return f"{value:,.0f}" if value is not None else "n/a"


def add_line_fields(embed: discord.Embed,
                    title: str,
                    lines: list[str],
                    empty_text: str,
                    continuation_title: Optional[str] = None):
    """Add all lines across as many embed fields as Discord needs."""
    if not lines:
        embed.add_field(name=title, value=empty_text, inline=False)
        return

    chunks = []
    current_lines = []
    current_size = 0

    for line in lines:
        clipped_line = clip_text(line, 1000)
        line_size = len(clipped_line) + 1

        if current_lines and current_size + line_size > 1000:
            chunks.append(current_lines)
            current_lines = []
            current_size = 0

        current_lines.append(clipped_line)
        current_size += line_size

    if current_lines:
        chunks.append(current_lines)

    for index, chunk in enumerate(chunks, 1):
        field_title = title if index == 1 else (continuation_title or f"{title} ({index})")
        embed.add_field(name=field_title, value="\n".join(chunk), inline=False)


def war_player_index(members_payload: dict, race: dict, historical_stats: dict) -> dict[str, dict]:
    """Return known war players keyed by tag from roster, current race, and history."""
    players: dict[str, dict] = {}

    for member in members_payload.get("items") or []:
        player_tag = member.get("tag")

        if player_tag:
            players[player_tag] = dict(member)

    current_clan = race.get("clan") or {}

    for participant in current_clan.get("participants") or []:
        player_tag = participant.get("tag")

        if not player_tag:
            continue

        player = players.setdefault(
            player_tag,
            {"tag": player_tag, "name": participant.get("name", "Unknown"), "role": "unknown"},
        )
        player["name"] = participant.get("name", player.get("name", "Unknown"))

    for player_tag, history in historical_stats.items():
        players.setdefault(
            player_tag,
            {"tag": player_tag, "name": history.get("name", "Unknown"), "role": "unknown"},
        )

    return players


def last_war_bottom_lines(race_log: dict,
                          clan_tag: Optional[str],
                          cutoff: dt.datetime,
                          members_payload: dict,
                          historical_stats: dict,
                          presence_map: dict,
                          now: dt.datetime) -> tuple[Optional[dt.datetime], list[str]]:
    """Return ranked rows for players below the top 40 in the last completed war."""
    completed_at, latest_clan = latest_completed_clan_race(race_log, clan_tag, cutoff)

    if latest_clan is None:
        return completed_at, []

    roster_by_tag = {
        member.get("tag"): member
        for member in members_payload.get("items") or []
        if member.get("tag")
    }
    ranked_participants = sorted(
        latest_clan.get("participants") or [],
        key=lambda participant: (
            int_value(participant.get("fame")),
            int_value(participant.get("decksUsed")),
            int_value(participant.get("decksUsedToday")),
            str(participant.get("name") or "").lower(),
        ),
        reverse=True,
    )
    rows = []

    for rank, participant in enumerate(ranked_participants, 1):
        if rank < LAST_WAR_BOTTOM_START_RANK:
            continue

        player_tag = participant.get("tag")

        if not player_tag:
            continue

        roster_member = roster_by_tag.get(player_tag)
        in_current_roster = roster_member is not None
        player_name = (roster_member or participant).get("name", "Unknown")
        role_text = role_label(roster_member) if in_current_roster else "⬜ Not in clan"
        status_text = "in clan" if in_current_roster else "not in clan anymore"
        history = historical_stats.get(player_tag, {})
        presence = presence_map.get(player_tag)
        first_seen_at = parse_iso_datetime(presence_value(presence, "first_seen_at"))
        first_seen_source = presence_value(presence, "first_seen_source")
        membership_at, membership_label = membership_context_date(presence, first_seen_at)
        full_entries = eligible_completed_entries(history, first_seen_at, first_seen_source)
        average_fame = average_entry_fame(full_entries)
        rows.append(
            f"{rank}. {role_text} {format_name(player_name)} - "
            f"{int_value(participant.get('fame')):,} last war, "
            f"{average_fame_text(average_fame)} avg/{len(full_entries)} full wars, "
            f"{membership_context_text(membership_at, membership_label, now)}, "
            f"status: {status_text}"
        )

    return completed_at, rows


def resolve_war_player(query: str, players_by_tag: dict[str, dict]) -> tuple[Optional[dict], Optional[str]]:
    """Resolve a player by exact/partial IGN or player tag."""
    value = query.strip()

    if not value:
        return None, "Enter an IGN, player tag, or Discord member."

    query_key = value.casefold()
    exact_name_matches = [
        player for player in players_by_tag.values()
        if str(player.get("name") or "").casefold() == query_key
    ]

    if len(exact_name_matches) == 1:
        return exact_name_matches[0], None

    if len(exact_name_matches) > 1:
        names = ", ".join(f"{format_name(player.get('name'))} `{player.get('tag')}`" for player in exact_name_matches[:8])
        return None, f"Multiple players are named `{value}`: {names}. Use a player tag."

    if is_likely_player_tag(value):
        player_tag = normalize_tag(value)
        player = players_by_tag.get(player_tag)

        if player:
            return player, None

        return None, f"I could not find player tag `{player_tag}` in the current roster or recent war history."

    partial_name_matches = [
        player for player in players_by_tag.values()
        if query_key in str(player.get("name") or "").casefold()
    ]

    if len(partial_name_matches) == 1:
        return partial_name_matches[0], None

    if len(partial_name_matches) > 1:
        names = ", ".join(f"{format_name(player.get('name'))} `{player.get('tag')}`" for player in partial_name_matches[:8])
        more = "" if len(partial_name_matches) <= 8 else f", and {len(partial_name_matches) - 8} more"
        return None, f"`{value}` matched multiple players: {names}{more}. Use the exact IGN or player tag."

    return None, f"I could not find `{value}` in the current roster or recent war history."


def recommendation_text(label: str, ok: bool, detail: str) -> str:
    """Format one recommendation status line."""
    status = "Yes" if ok else "No"
    return f"{label}: **{status}** - {detail}"


def build_player_war_stats_embed(target: dict,
                                 race: dict,
                                 members_payload: dict,
                                 race_log: dict,
                                 presence_map: dict,
                                 kick_threshold: int,
                                 promotion_threshold: int) -> discord.Embed:
    """Build current and rolling war stats for one player."""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=ROLLING_WAR_DAYS)
    current_clan = race.get("clan") or {}
    current_participants = current_clan.get("participants") or []
    current_by_tag = {participant.get("tag"): participant for participant in current_participants}
    roster_by_tag = {
        member.get("tag"): member
        for member in members_payload.get("items") or []
        if member.get("tag")
    }
    historical_stats, completed_race_dates = collect_completed_war_stats(race_log, current_clan.get("tag"), cutoff)
    race_start = estimate_current_race_start(race, race_log, now)
    last_completed_at = max(completed_race_dates) if completed_race_dates else None
    active_completed_at = last_completed_at if is_training_period(race) else None

    player_tag = target.get("tag")
    member = roster_by_tag.get(player_tag, target)
    player_name = member.get("name", target.get("name", "Unknown"))
    participant = current_by_tag.get(player_tag, {})
    current_fame = int_value(participant.get("fame"))
    decks_today = min(4, int_value(participant.get("decksUsedToday")))
    decks_total = int_value(participant.get("decksUsed"))
    history = historical_stats.get(player_tag, {})
    presence = presence_map.get(player_tag)
    first_seen_at = parse_iso_datetime(presence_value(presence, "first_seen_at"))
    first_seen_source = presence_value(presence, "first_seen_source")
    joined_at = known_join_date(presence)
    tenure_at = joined_at or first_seen_at
    last_seen_at = parse_iso_datetime(presence_value(presence, "last_seen_at"))
    full_entries = sorted(
        eligible_completed_entries(history, first_seen_at, first_seen_source),
        key=lambda entry: entry["date"],
        reverse=True,
    )
    entries = sorted(history.get("entries", []), key=lambda entry: entry["date"], reverse=True)
    race_count = len(full_entries)
    average_fame = average_entry_fame(full_entries)
    full_scores = [entry["fame"] for entry in full_entries]
    best_fame = max(full_scores) if full_scores else None
    low_fame = min(full_scores) if full_scores else None
    active_fame, score_label = active_score(current_fame, history, active_completed_at, first_seen_at, first_seen_source)
    active_title = "Training Period / Last War" if active_completed_at is not None else "Current War"
    fame_label = "Last war fame" if active_completed_at is not None else "Fame"
    decks_label = "training decks used" if is_training_period(race) else "decks used"
    has_leaderboard_tenure = has_min_tenure(tenure_at, now, MIN_LEADERBOARD_DAYS)
    tracked_after_race_start = first_seen_at is None or first_seen_at > race_start + dt.timedelta(hours=6)
    low_active = active_fame is not None and active_fame < kick_threshold
    low_or_missing_average = average_fame is None or average_fame < kick_threshold
    short_history_good_war = has_short_history_good_war(full_entries, kick_threshold)
    should_kick_demote = should_suggest_kick_demotion(active_fame, average_fame, full_entries, kick_threshold)
    should_promote = (
        average_fame is not None
        and average_fame >= promotion_threshold
        and race_count >= MIN_PROMOTION_WARS
        and has_leaderboard_tenure
        and active_fame is not None
        and active_fame >= kick_threshold
        and can_be_promoted(member)
    )
    roster_status = "in current clan" if player_tag in roster_by_tag else "not in current clan"

    embed = discord.Embed(
        title=f"{format_name(player_name)} War Stats",
        description=f"{role_label(member)} `{player_tag or 'unknown tag'}` - {roster_status}",
        color=discord.Color.green() if active_fame is not None and active_fame >= kick_threshold else discord.Color.gold(),
        timestamp=now,
    )
    embed.add_field(
        name=active_title,
        value=(
            f"{fame_label}: **{fame_text(active_fame)}**\n"
            f"Decks today: **{decks_today}/4 {decks_label}**\n"
            f"Decks total: **{decks_total} {decks_label}**\n"
            f"Last completed war: **{short_date(last_completed_at)}**"
        ),
        inline=False,
    )

    average_text = f"{average_fame:,.0f}" if average_fame is not None else "n/a"
    best_text = f"{best_fame:,}" if best_fame is not None else "n/a"
    low_text = f"{low_fame:,}" if low_fame is not None else "n/a"
    recent_lines = [
        (
            f"{short_date(entry['date'])}: {entry['fame']:,}"
            if is_full_completed_war(entry["date"], first_seen_at, first_seen_source, entry["fame"])
            else f"{short_date(entry['date'])}: {entry['fame']:,} (partial; not counted)"
        )
        for entry in entries[:5]
    ]
    embed.add_field(
        name=f"Rolling {ROLLING_WAR_DAYS}-Day Full-War History",
        value=(
            f"Average: **{average_text}** over **{race_count}** full completed wars\n"
            f"Best / Low: **{best_text}** / **{low_text}**\n"
            f"Recent: {', '.join(recent_lines) if recent_lines else 'No completed wars in window'}"
        ),
        inline=False,
    )

    joined_line = f"{short_date(joined_at)} ({days_ago_label(joined_at, now)})" if joined_at else None
    first_seen_line = f"{short_date(first_seen_at)} ({days_ago_label(first_seen_at, now)})"
    last_seen_line = f"{short_date(last_seen_at)} ({days_ago_label(last_seen_at, now)})"
    context_lines = []

    if joined_line:
        context_lines.append(f"Joined: **{joined_line}**")

    context_lines.extend(
        [
            f"First seen by bot/API: **{first_seen_line}**",
            f"Last seen: **{last_seen_line}**",
            f"In current roster: **{'Yes' if player_tag in roster_by_tag else 'No - not in clan anymore'}**",
        ]
    )
    embed.add_field(
        name="Clan Context",
        value="\n".join(context_lines),
        inline=False,
    )

    if should_kick_demote:
        if average_fame is not None:
            kick_detail = f"{score_label} and rolling average are below threshold"
        elif tracked_after_race_start:
            kick_detail = f"{score_label} is below threshold; verify join timing"
        else:
            kick_detail = f"{score_label} is below threshold and no full-war average exists"
    elif active_fame is None:
        kick_detail = "no full-war score is available yet"
    elif active_fame >= kick_threshold:
        kick_detail = f"{score_label} is at or above threshold"
    elif average_fame is not None and average_fame >= kick_threshold:
        kick_detail = "rolling average is at or above threshold"
    elif short_history_good_war:
        kick_detail = f"short history includes a {kick_threshold:,}+ full war"
    else:
        kick_detail = "not enough completed-war history"

    if should_promote:
        promotion_detail = "meets average, tenure, active-score, and role requirements"
    elif not can_be_promoted(member):
        promotion_detail = "already co-leader or leader"
    elif average_fame is None or average_fame < promotion_threshold:
        promotion_detail = "average is below promotion threshold"
    elif race_count < MIN_PROMOTION_WARS:
        promotion_detail = f"requires {MIN_PROMOTION_WARS}+ full completed wars"
    elif not has_leaderboard_tenure:
        promotion_detail = f"requires {MIN_LEADERBOARD_DAYS}+ days joined/seen"
    elif active_fame is None:
        promotion_detail = "no full-war score is available yet"
    elif active_fame < kick_threshold:
        promotion_detail = f"{score_label} is below kick threshold"
    else:
        promotion_detail = "does not meet promotion rules"

    leaderboard_ok = average_fame is not None and race_count >= MIN_LEADERBOARD_WARS and has_leaderboard_tenure
    leaderboard_detail = (
        f"requires {MIN_LEADERBOARD_WARS}+ full completed wars and {MIN_LEADERBOARD_DAYS}+ days joined/seen"
        if not leaderboard_ok
        else "eligible for the rolling leaderboard"
    )
    embed.add_field(
        name="Recommendations",
        value=(
            f"{recommendation_text('Kick/Demotion', should_kick_demote, kick_detail)}\n"
            f"{recommendation_text('Promotion', should_promote, promotion_detail)}\n"
            f"{recommendation_text('Leaderboard', leaderboard_ok, leaderboard_detail)}"
        ),
        inline=False,
    )

    completed_count = len(completed_race_dates)
    embed.set_footer(
        text=(
            f"{completed_count} completed wars in window. "
            f"Thresholds: kick {kick_threshold:,}, promotion {promotion_threshold:,} avg."
        )
    )
    return embed


def build_enhanced_war_stats_embed(race: dict,
                                   members_payload: dict,
                                   race_log: dict,
                                   presence_map: dict,
                                   kick_threshold: int,
                                   promotion_threshold: int) -> discord.Embed:
    """Build current, rolling, and kick-review war stats."""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=ROLLING_WAR_DAYS)
    current_clan = race.get("clan") or {}
    members = members_payload.get("items") or []
    current_participants = current_clan.get("participants") or []
    current_by_tag = {participant.get("tag"): participant for participant in current_participants}
    historical_stats, completed_race_dates = collect_completed_war_stats(race_log, current_clan.get("tag"), cutoff)
    race_start = estimate_current_race_start(race, race_log, now)
    last_completed_at = max(completed_race_dates) if completed_race_dates else None
    active_completed_at = last_completed_at if is_training_period(race) else None
    active_total_fame = (
        sum(completed_war_score(history, active_completed_at) for history in historical_stats.values())
        if active_completed_at is not None
        else sum(int_value(participant.get("fame")) for participant in current_participants)
    )
    active_summary_label = "Last war fame" if active_completed_at is not None else "Fame"
    active_row_label = "last war" if active_completed_at is not None else "current"
    decks_today_label = "training decks used" if is_training_period(race) else "decks used"
    decks_total_label = "training decks used" if is_training_period(race) else "decks used"

    decks_today = sum(int_value(participant.get("decksUsedToday")) for participant in current_participants)
    decks_total = sum(int_value(participant.get("decksUsed")) for participant in current_participants)
    period_index = int_value(race.get("periodIndex"))
    current_week_day = (period_index % 7) + 1
    period_type = format_name(race.get("periodType") or "unknown")
    field_name = "Training Period" if active_completed_at is not None else "Current War"

    embed = discord.Embed(
        title=f"{current_clan.get('name', 'Clan')} War Stats",
        description=f"Current race plus completed wars since {short_date(cutoff)}.",
        color=discord.Color.blue(),
        timestamp=now,
    )
    embed.add_field(
        name=field_name,
        value=(
            f"{active_summary_label}: **{active_total_fame:,}**\n"
            f"Decks today: **{decks_today}/200 {decks_today_label}**\n"
            f"Decks total: **{decks_total} {decks_total_label}**\n"
            f"Period: **{period_type} day {current_week_day}/7**\n"
            f"Last completed war: **{short_date(last_completed_at)}**\n"
            f"Kick threshold: **{kick_threshold:,} war fame**\n"
            f"Promotion threshold: **{promotion_threshold:,} avg war fame**"
        ),
        inline=False,
    )

    rolling_rows = []
    suggested_rows = []
    promotion_rows = []

    for member in members:
        player_tag = member.get("tag")

        if not player_tag:
            continue

        player_name = member.get("name", "Unknown")
        member_role = role_label(member)
        participant = current_by_tag.get(player_tag, {})
        current_fame = int_value(participant.get("fame"))
        history = historical_stats.get(player_tag, {})
        presence = presence_map.get(player_tag)
        first_seen_at = parse_iso_datetime(presence_value(presence, "first_seen_at"))
        first_seen_source = presence_value(presence, "first_seen_source")
        membership_at, membership_label = membership_context_date(presence, first_seen_at)
        full_entries = eligible_completed_entries(history, first_seen_at, first_seen_source)
        race_count = len(full_entries)
        average_fame = average_entry_fame(full_entries)
        active_fame, score_label = active_score(current_fame, history, active_completed_at, first_seen_at, first_seen_source)
        has_leaderboard_tenure = has_min_tenure(membership_at, now, MIN_LEADERBOARD_DAYS)
        tracked_after_race_start = first_seen_at is None or first_seen_at > race_start + dt.timedelta(hours=6)

        if average_fame is not None and race_count >= MIN_LEADERBOARD_WARS and has_leaderboard_tenure:
            rolling_rows.append((average_fame, race_count, member_role, player_name, active_fame, score_label, membership_at, membership_label))

        if (average_fame is not None
                and average_fame >= promotion_threshold
                and race_count >= MIN_PROMOTION_WARS
                and has_leaderboard_tenure
                and active_fame is not None
                and active_fame >= kick_threshold
                and can_be_promoted(member)):
            promotion_rows.append((average_fame, race_count, member_role, player_name, active_fame, score_label, membership_at, membership_label))

        if should_suggest_kick_demotion(active_fame, average_fame, full_entries, kick_threshold):
            if average_fame is not None:
                reason = f"{active_row_label} and rolling average below threshold"
            elif tracked_after_race_start:
                reason = f"{active_row_label} below threshold; verify join timing"
            else:
                reason = f"{active_row_label} below threshold; no completed-war average yet"

            suggested_rows.append(
                (
                    active_fame,
                    average_fame if average_fame is not None else -1,
                    race_count,
                    player_name.lower(),
                    score_line(
                        member_role,
                        player_name,
                        active_fame,
                        score_label,
                        average_fame,
                        race_count,
                        membership_at,
                        membership_label,
                        now,
                        reason,
                    ),
                )
            )

    rolling_rows.sort(key=lambda row: (row[0], row[1], row[3].lower()), reverse=True)
    rolling_lines = [
        (
            f"{index}. {role_text} {format_name(name)} - {average:,.0f} avg/{race_count} full wars, "
            f"{fame_text(active_fame)} {score_label}, {membership_label} {short_date(membership_at)}"
        )
        for index, (
            average,
            race_count,
            role_text,
            name,
            active_fame,
            score_label,
            membership_at,
            membership_label,
        ) in enumerate(rolling_rows[:10], 1)
    ]
    embed.add_field(
        name=f"Rolling {ROLLING_WAR_DAYS}-Day Leaders",
        value=clip_text(
            "\n".join(rolling_lines)
            or f"No eligible members yet. Requires {MIN_LEADERBOARD_WARS}+ full completed wars and {MIN_LEADERBOARD_DAYS}+ days joined/seen."
        ),
        inline=False,
    )

    promotion_rows.sort(key=lambda row: (row[0], row[1], row[3].lower()), reverse=True)
    promotion_lines = [
        (
            f"{role_text} {format_name(name)} - {average:,.0f} avg/{race_count} full wars, "
            f"{fame_text(active_fame)} {score_label}, {membership_label} {short_date(membership_at)}"
        )
        for average, race_count, role_text, name, active_fame, score_label, membership_at, membership_label in promotion_rows
    ]
    add_line_fields(
        embed,
        "Suggested Promotions",
        promotion_lines,
        f"No promotion suggestions. Requires {promotion_threshold:,}+ average, {MIN_PROMOTION_WARS}+ full wars, and {MIN_LEADERBOARD_DAYS}+ days joined/seen.",
    )

    suggested_rows.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    suggested_lines = [row[4] for row in suggested_rows]
    add_line_fields(
        embed,
        "Suggested Kick/Demotion",
        suggested_lines,
        "No kick/demotion suggestions at the current threshold.",
        continuation_title="More Candidates",
    )

    completed_count = len(completed_race_dates)
    embed.set_footer(
        text=(
            f"{completed_count} completed wars in window. "
            "Joined dates are manual when configured; otherwise seen means bot/API first observed."
        )
    )
    return embed


def build_last_war_bottom_embed(race: dict,
                                members_payload: dict,
                                race_log: dict,
                                presence_map: dict) -> discord.Embed:
    """Build a last completed-war audit for players ranked below the top 40."""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=ROLLING_WAR_DAYS)
    current_clan = race.get("clan") or {}
    historical_stats, completed_race_dates = collect_completed_war_stats(race_log, current_clan.get("tag"), cutoff)
    last_war_at, bottom_lines = last_war_bottom_lines(
        race_log,
        current_clan.get("tag"),
        cutoff,
        members_payload,
        historical_stats,
        presence_map,
        now,
    )
    embed = discord.Embed(
        title=f"{current_clan.get('name', 'Clan')} Last War Rank {LAST_WAR_BOTTOM_START_RANK}+",
        description=f"Latest completed war plus rolling full-war averages since {short_date(cutoff)}.",
        color=discord.Color.orange(),
        timestamp=now,
    )
    embed.add_field(
        name="Last Completed War",
        value=(
            f"Completed: **{short_date(last_war_at)}**\n"
            f"Ranks shown: **{LAST_WAR_BOTTOM_START_RANK}+**\n"
            f"Completed wars in window: **{len(completed_race_dates)}**"
        ),
        inline=False,
    )
    empty_bottom_text = (
        "No completed war found in the rolling window."
        if last_war_at is None
        else f"No players ranked {LAST_WAR_BOTTOM_START_RANK}+ in the last completed war."
    )
    add_line_fields(
        embed,
        f"Rank {LAST_WAR_BOTTOM_START_RANK}+ Players",
        bottom_lines,
        empty_bottom_text,
        continuation_title=f"More Rank {LAST_WAR_BOTTOM_START_RANK}+",
    )
    embed.set_footer(
        text=(
            "Status is based on the current clan roster. "
            "Joined dates are manual when configured; otherwise seen means bot/API first observed."
        )
    )
    return embed


class MicroBot(discord.Client):
    """Minimal Discord client with slash commands."""

    def __init__(self, settings: Settings, store: Store, clash: ClashClient):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.settings = settings
        self.store = store
        self.clash = clash
        self.tree = app_commands.CommandTree(self)
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._join_date_task: Optional[asyncio.Task] = None

    async def setup_hook(self):
        """Register slash commands."""
        guild = discord.Object(id=self.settings.discord_guild_id) if self.settings.discord_guild_id else None

        if guild:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        """Log startup."""
        LOG.info("Micro bot ready as %s", self.user)

        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self.write_heartbeat_loop())

        if self._join_date_task is None or self._join_date_task.done():
            self._join_date_task = asyncio.create_task(self.sync_join_dates_loop())

    async def write_heartbeat_loop(self):
        """Write a liveness marker for systemd diagnostics/watchdog scripts."""
        heartbeat_path = Path(self.settings.heartbeat_path)
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)

        while not self.is_closed():
            try:
                now = dt.datetime.now(dt.timezone.utc).isoformat()
                latency_ms = self.latency * 1000 if self.latency is not None else -1
                heartbeat_path.write_text(
                    f"ready={self.is_ready()}\n"
                    f"user={self.user}\n"
                    f"latency_ms={latency_ms:.0f}\n"
                    f"updated_at={now}\n",
                    encoding="utf-8",
                )
            except OSError:
                LOG.exception("Failed to write heartbeat file")

            await asyncio.sleep(60)

    async def sync_join_dates_loop(self):
        """Track current-roster join dates on startup and then weekly."""
        await self.wait_until_ready()

        while not self.is_closed():
            try:
                inserted, joined_at, source = await asyncio.to_thread(
                    sync_roster_join_dates,
                    self.store,
                    self.clash,
                    self.settings.clan_tag,
                    dt.datetime.now(dt.timezone.utc),
                )
                LOG.info(
                    "Join-date sync complete: inserted=%s joined_at=%s source=%s",
                    inserted,
                    joined_at.date().isoformat(),
                    source,
                )
            except ClashApiError:
                LOG.exception("Join-date sync failed because the Clash Royale API is unavailable")
            except Exception:
                LOG.exception("Join-date sync failed unexpectedly")

            await asyncio.sleep(JOIN_DATE_SYNC_INTERVAL_SECONDS)


def build_bot() -> MicroBot:
    """Build the bot and commands."""
    settings = load_settings()
    store = Store(settings.database_path)
    store.initialize()
    clash = ClashClient(settings.clash_api_token)
    bot = MicroBot(settings, store, clash)

    def current_verified_role_id() -> Optional[int]:
        """Return the configured verified role, preferring the database setting."""
        return store.get_verified_role_id() or settings.verified_role_id

    def current_elder_role_id() -> Optional[int]:
        """Return the configured Discord elder role."""
        return store.get_elder_role_id()

    def current_coleader_role_id() -> Optional[int]:
        """Return the configured Discord co-leader role."""
        return store.get_coleader_role_id()

    def current_verification_channel_id() -> Optional[int]:
        """Return the configured verification review channel."""
        return store.get_verification_channel_id()

    def current_kick_threshold() -> int:
        """Return the configured minimum war fame for kick suggestions."""
        return store.get_kick_threshold() or DEFAULT_KICK_THRESHOLD

    def current_promotion_threshold() -> int:
        """Return the configured average war fame for promotion suggestions."""
        return store.get_promotion_threshold() or DEFAULT_PROMOTION_THRESHOLD

    def current_auto_verification_enabled() -> bool:
        """Return whether /verify should immediately link current clan tags."""
        return store.get_auto_verification_enabled()

    def find_guild_role_by_name(guild: discord.Guild, role_names: set[str]) -> Optional[discord.Role]:
        """Return the first guild role matching one of the configured names."""
        for role in guild.roles:
            if role.name.casefold() in role_names:
                return role

        return None

    def resolve_guild_role(guild: discord.Guild,
                           role_id: Optional[int],
                           fallback_names: set[str]) -> Optional[discord.Role]:
        """Find a configured role by id, falling back to a conventional role name."""
        if role_id is not None:
            role = guild.get_role(role_id)

            if role is not None:
                return role

        return find_guild_role_by_name(guild, fallback_names)

    def role_setup_notes(interaction: discord.Interaction, role: discord.Role) -> list[str]:
        """Return setup notes for a Discord role the bot will assign."""
        notes = []
        bot_member = interaction.guild.me if interaction.guild else None

        if bot_member and bot_member.top_role <= role:
            notes.append("Move the bot's role above this role in Server Settings > Roles so it can assign it.")

        if not interaction.app_permissions.manage_roles:
            notes.append("The bot also needs the Manage Roles permission.")

        return notes

    async def assign_role(interaction: discord.Interaction,
                          member: discord.Member,
                          role: discord.Role,
                          reason: str) -> Optional[str]:
        """Assign a Discord role and return a user-facing note."""
        if role in member.roles:
            return None

        bot_member = interaction.guild.me if interaction.guild else None

        if bot_member and bot_member.top_role <= role:
            return f"I could not assign {role.mention}. My role must be above it in Server Settings > Roles."

        if not interaction.app_permissions.manage_roles:
            return f"I could not assign {role.mention}. I need the Manage Roles permission."

        try:
            await member.add_roles(role, reason=reason)
        except discord.Forbidden:
            return f"I could not assign {role.mention}. I need Manage Roles and a role above it."
        except discord.HTTPException:
            return f"Discord rejected the {role.mention} role assignment."

        return f"Assigned {role.mention}."

    async def current_clash_role(player: dict) -> str:
        """Return the player's current in-game clan role."""
        role_key = player_role_key(player)

        if role_key is not None:
            return role_key

        if not settings.clan_tag:
            return "member"

        try:
            members = await asyncio.to_thread(clash.get_clan_members, settings.clan_tag)
        except ClashApiError:
            return "member"

        player_tag = normalize_tag(player.get("tag", ""))

        for member in members.get("items") or []:
            if normalize_tag(member.get("tag", "")) == player_tag:
                return normalized_role(member)

        return "member"

    async def resolve_current_clan_member(query: str) -> tuple[Optional[dict], Optional[str]]:
        """Resolve a current clan member by player tag or IGN."""
        if not settings.clan_tag:
            return None, "No clan tag is configured for this bot."

        try:
            members = await asyncio.to_thread(clash.get_clan_members, settings.clan_tag)
        except ClashApiError:
            return None, "The Clash Royale API is unavailable. Try again later."

        players_by_tag = {
            member["tag"]: member
            for member in members.get("items") or []
            if member.get("tag")
        }
        return resolve_war_player(query, players_by_tag)

    async def add_verified_role(interaction: discord.Interaction, member: discord.Member) -> Optional[str]:
        """Assign the configured verified role and return a user-facing note."""
        role_id = current_verified_role_id()

        if role_id is None:
            return "No verified role is configured yet. Run `/set_verified_role` when the role is ready."

        if interaction.guild is None:
            return "The account is verified, but roles can only be assigned inside the server."

        role = interaction.guild.get_role(role_id)

        if role is None:
            return "The account is verified, but the configured verified role was not found."

        return await assign_role(interaction, member, role, "Clash Royale clan verification")

    async def add_clash_status_role(interaction: discord.Interaction,
                                    member: discord.Member,
                                    player: dict) -> Optional[str]:
        """Assign an optional Discord role that mirrors the player's in-game clan role."""
        if interaction.guild is None:
            return None

        role_key = await current_clash_role(player)

        if role_key == "elder":
            role = resolve_guild_role(
                interaction.guild,
                current_elder_role_id(),
                DEFAULT_ELDER_ROLE_NAMES,
            )

            if role is None:
                return "No Discord Elder role was found. Create `Elder` or run `/set_elder_role`."

            return await assign_role(interaction, member, role, "Clash Royale elder verification")

        if role_key in {"coleader", "leader"}:
            role = resolve_guild_role(
                interaction.guild,
                current_coleader_role_id(),
                DEFAULT_COLEADER_ROLE_NAMES,
            )

            if role is None:
                return "No Discord Co-Leader role was found. Create `Co-Leader` or run `/set_coleader_role`."

            return await assign_role(interaction, member, role, "Clash Royale co-leader verification")

        return None

    async def remove_verified_role(interaction: discord.Interaction, member: discord.Member) -> Optional[str]:
        """Remove the configured verified role and return a user-facing note."""
        role_id = current_verified_role_id()

        if role_id is None:
            return None

        if interaction.guild is None:
            return "Roles can only be changed inside the server."

        role = interaction.guild.get_role(role_id)

        if role is None:
            return "The configured verified role was not found."

        if role not in member.roles:
            return None

        try:
            await member.remove_roles(role, reason="Clash Royale verification removed")
        except discord.Forbidden:
            return "I do not have permission to remove the verified role."
        except discord.HTTPException:
            return "Discord rejected the verified role removal."

        return f"Removed {role.mention}."

    async def remove_clash_status_roles(interaction: discord.Interaction,
                                        member: discord.Member) -> list[str]:
        """Remove Discord roles that mirror in-game clan status."""
        if interaction.guild is None:
            return []

        roles = [
            resolve_guild_role(interaction.guild, current_elder_role_id(), DEFAULT_ELDER_ROLE_NAMES),
            resolve_guild_role(interaction.guild, current_coleader_role_id(), DEFAULT_COLEADER_ROLE_NAMES),
        ]
        notes = []
        seen_role_ids = set()

        for role in roles:
            if role is None or role.id in seen_role_ids:
                continue

            seen_role_ids.add(role.id)

            if role not in member.roles:
                continue

            try:
                await member.remove_roles(role, reason="Clash Royale verification removed")
            except discord.Forbidden:
                notes.append(f"I do not have permission to remove {role.mention}.")
            except discord.HTTPException:
                notes.append(f"Discord rejected removal of {role.mention}.")
            else:
                notes.append(f"Removed {role.mention}.")

        return notes

    async def set_member_nickname(member: discord.Member, nickname: str) -> Optional[str]:
        """Set a member's server nickname and return a user-facing note."""
        if member.nick == nickname:
            return None

        if member.guild.owner_id == member.id:
            return "Discord does not allow bots to update the server owner's nickname."

        bot_member = member.guild.me

        if bot_member and not bot_member.guild_permissions.manage_nicknames:
            return "I could not update the nickname. I need Manage Nicknames."

        if bot_member and member.top_role >= bot_member.top_role:
            return "I could not update the nickname. My role must be above that member's highest role."

        try:
            await member.edit(nick=nickname, reason="Clash Royale clan verification")
        except discord.Forbidden:
            return "I could not update the nickname. I need Manage Nicknames and a role above that member."
        except discord.HTTPException:
            return "Discord rejected the nickname update."

        return f"Updated nickname to `{nickname}`."

    async def announce_verification_challenge(interaction: discord.Interaction,
                                              player: dict,
                                              code: str,
                                              expires_at: str) -> Optional[str]:
        """Post a pending verification request to the configured leader channel."""
        channel_id = current_verification_channel_id()
        channel = None

        if channel_id is None and interaction.guild:
            channel = discord.utils.get(
                interaction.guild.text_channels,
                name=DEFAULT_VERIFICATION_CHANNEL_NAME,
            )

            if channel:
                store.set_verification_channel_id(channel.id)
                channel_id = channel.id

        if channel_id is None:
            return (
                "No leader verification channel is configured yet. "
                f"Create `#{DEFAULT_VERIFICATION_CHANNEL_NAME}` or run `/set_verification_channel`."
            )

        if channel is None:
            channel = bot.get_channel(channel_id)

        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except discord.HTTPException:
                return "I could not find the configured leader verification channel."

        if not hasattr(channel, "send"):
            return "The configured verification destination is not a text channel."

        embed = discord.Embed(
            title="Pending Clash Royale Verification",
            color=discord.Color.gold(),
            timestamp=dt.datetime.now(dt.timezone.utc),
        )
        embed.add_field(name="Discord Member", value=interaction.user.mention, inline=False)
        embed.add_field(name="Player", value=f"{player['name']} `{player['tag']}`", inline=False)
        embed.add_field(name="Clan Chat Code", value=f"`{code}`", inline=True)
        embed.add_field(name="Expires", value=f"`{expires_at}`", inline=True)
        embed.add_field(
            name="Leader Action",
            value=(
                f"After an admin or Elder sees the code in clan chat, run `/confirm_verification member:{interaction.user.mention}`.\n"
                f"Fallback/direct verify with tag: `/confirm_verification member:{interaction.user.mention} player_tag:{player['tag']}`"
            ),
            inline=False,
        )

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return "I do not have permission to post in the configured leader verification channel."
        except discord.HTTPException:
            return "Discord rejected the leader verification channel message."

        return f"I also posted this request in <#{channel_id}>."

    async def announce_auto_verification(interaction: discord.Interaction,
                                         player: dict,
                                         clan_tag: Optional[str],
                                         clan_name: Optional[str]) -> Optional[str]:
        """Post an auto-verification audit message to the leader channel."""
        channel_id = current_verification_channel_id()
        channel = None

        if channel_id is None and interaction.guild:
            channel = discord.utils.get(
                interaction.guild.text_channels,
                name=DEFAULT_VERIFICATION_CHANNEL_NAME,
            )

            if channel:
                store.set_verification_channel_id(channel.id)
                channel_id = channel.id

        if channel_id is None:
            return (
                "No leader verification channel is configured yet, so I could not post the auto-verification audit."
            )

        if channel is None:
            channel = bot.get_channel(channel_id)

        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except discord.HTTPException:
                return "I could not find the configured leader verification channel for the auto-verification audit."

        if not hasattr(channel, "send"):
            return "The configured verification destination is not a text channel."

        embed = discord.Embed(
            title="Auto Confirmed Clash Royale Verification",
            color=discord.Color.green(),
            timestamp=dt.datetime.now(dt.timezone.utc),
        )
        embed.add_field(name="Discord Member", value=interaction.user.mention, inline=False)
        embed.add_field(name="Player", value=f"{player['name']} `{player['tag']}`", inline=False)
        embed.add_field(name="Mode", value="Auto confirmed by current clan tag", inline=False)

        if clan_name:
            embed.add_field(name="Clan", value=f"{clan_name} `{clan_tag}`", inline=False)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return "I do not have permission to post the auto-verification audit in the configured leader channel."
        except discord.HTTPException:
            return "Discord rejected the auto-verification audit message."

        return f"I also posted the auto-verification audit in <#{channel_id}>."

    @bot.tree.command(name="bot_health", description="Show whether the lightweight bot is online.")
    async def bot_health(interaction: discord.Interaction):
        await interaction.response.send_message("Online. SQLite store is initialized.", ephemeral=True)

    @bot.tree.command(name="set_verified_role", description="Set the role assigned after Clash Royale verification.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(role="Role to assign after a member is verified")
    async def set_verified_role(interaction: discord.Interaction, role: discord.Role):
        if role.is_default():
            await interaction.response.send_message("Choose a normal role, not @everyone.", ephemeral=True)
            return

        notes = role_setup_notes(interaction, role)
        store.set_verified_role_id(role.id)
        message = f"Verified role set to {role.mention}."

        if notes:
            message += "\n" + "\n".join(notes)

        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name="set_elder_role", description="Set the Discord role assigned to in-game Clash elders.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(role="Discord role to assign when a verified player is an in-game Elder")
    async def set_elder_role(interaction: discord.Interaction, role: discord.Role):
        if role.is_default():
            await interaction.response.send_message("Choose a normal role, not @everyone.", ephemeral=True)
            return

        notes = role_setup_notes(interaction, role)
        store.set_elder_role_id(role.id)
        message = f"Elder role set to {role.mention}."

        if notes:
            message += "\n" + "\n".join(notes)

        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name="set_coleader_role", description="Set the Discord role assigned to Clash co-leaders/leaders.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(role="Discord role to assign when a verified player is an in-game Co-Leader or Leader")
    async def set_coleader_role(interaction: discord.Interaction, role: discord.Role):
        if role.is_default():
            await interaction.response.send_message("Choose a normal role, not @everyone.", ephemeral=True)
            return

        notes = role_setup_notes(interaction, role)
        store.set_coleader_role_id(role.id)
        message = f"Co-Leader role set to {role.mention}."

        if notes:
            message += "\n" + "\n".join(notes)

        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name="set_verification_channel", description="Set the leader channel for verification requests.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(channel="Leader-only channel where pending verification requests should be posted")
    async def set_verification_channel(interaction: discord.Interaction, channel: discord.TextChannel):
        notes = []
        bot_member = interaction.guild.me if interaction.guild else None

        if bot_member:
            permissions = channel.permissions_for(bot_member)

            if not permissions.view_channel:
                notes.append("I need View Channel in that channel.")

            if not permissions.send_messages:
                notes.append("I need Send Messages in that channel.")

            if not permissions.embed_links:
                notes.append("I need Embed Links in that channel.")

        store.set_verification_channel_id(channel.id)
        message = f"Leader verification channel set to {channel.mention}."

        if notes:
            message += "\n" + "\n".join(notes)

        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name="set_auto_verification", description="Enable or disable automatic verification by clan tag.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(enabled="If true, /verify immediately links player tags currently in the clan")
    async def set_auto_verification(interaction: discord.Interaction, enabled: bool):
        store.set_auto_verification_enabled(enabled)
        state = "enabled" if enabled else "disabled"
        detail = (
            "Members who run `/verify player_tag:#TAG` will be auto confirmed if that tag is currently in the clan."
            if enabled
            else "Members who run `/verify` will receive a clan-chat code for leader confirmation."
        )
        await interaction.response.send_message(
            f"Auto verification is now `{state}`.\n{detail}",
            ephemeral=True,
        )

    @bot.tree.command(name="verification_config", description="Show verification role configuration.")
    @app_commands.checks.has_permissions(administrator=True)
    async def verification_config(interaction: discord.Interaction):
        role_id = current_verified_role_id()
        elder_role_id = current_elder_role_id()
        coleader_role_id = current_coleader_role_id()
        channel_id = current_verification_channel_id()
        lines = []

        if role_id is None:
            lines.append("Verified role: not configured")
        else:
            role = interaction.guild.get_role(role_id) if interaction.guild else None
            role_label = role.mention if role else f"`{role_id}` (not found)"
            lines.append(f"Verified role: {role_label}")

        if interaction.guild:
            elder_role = resolve_guild_role(
                interaction.guild,
                elder_role_id,
                DEFAULT_ELDER_ROLE_NAMES,
            )
            coleader_role = resolve_guild_role(
                interaction.guild,
                coleader_role_id,
                DEFAULT_COLEADER_ROLE_NAMES,
            )
        else:
            elder_role = None
            coleader_role = None

        if elder_role:
            source = "configured" if elder_role_id else "auto-detected by name"
            lines.append(f"Elder role: {elder_role.mention} ({source})")
        elif elder_role_id:
            lines.append(f"Elder role: `{elder_role_id}` (not found)")
        else:
            lines.append("Elder role: not configured; will auto-detect a role named `Elder`")

        if coleader_role:
            source = "configured" if coleader_role_id else "auto-detected by name"
            lines.append(f"Co-Leader role: {coleader_role.mention} ({source})")
        elif coleader_role_id:
            lines.append(f"Co-Leader role: `{coleader_role_id}` (not found)")
        else:
            lines.append("Co-Leader role: not configured; will auto-detect a role named `Co-Leader`")

        if channel_id is None:
            lines.append("Leader verification channel: not configured")
        else:
            channel = bot.get_channel(channel_id)
            channel_label = channel.mention if channel else f"`{channel_id}` (not found)"
            lines.append(f"Leader verification channel: {channel_label}")

        lines.append(f"Auto verification: {'enabled' if current_auto_verification_enabled() else 'disabled'}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @bot.tree.command(name="set_kick_threshold", description="Set minimum war fame for kick suggestions.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(min_fame="Minimum current or rolling war fame expected from members")
    async def set_kick_threshold(interaction: discord.Interaction, min_fame: int):
        if min_fame < 0:
            await interaction.response.send_message("Kick threshold must be 0 or higher.", ephemeral=True)
            return

        store.set_kick_threshold(min_fame)
        await interaction.response.send_message(
            f"Kick suggestion threshold set to `{min_fame:,}` war fame.",
            ephemeral=True,
        )

    @bot.tree.command(name="set_promotion_threshold", description="Set average war fame for promotion suggestions.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(min_average_fame="Minimum rolling average war fame for promotion suggestions")
    async def set_promotion_threshold(interaction: discord.Interaction, min_average_fame: int):
        if min_average_fame < 0:
            await interaction.response.send_message("Promotion threshold must be 0 or higher.", ephemeral=True)
            return

        store.set_promotion_threshold(min_average_fame)
        await interaction.response.send_message(
            f"Promotion suggestion threshold set to `{min_average_fame:,}` average war fame.",
            ephemeral=True,
        )

    @bot.tree.command(name="set_join_date", description="Set a known clan join date for a member.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(player="Current clan member IGN or player tag")
    @app_commands.describe(joined_on="Known join date in YYYY-MM-DD format")
    async def set_join_date(interaction: discord.Interaction, player: str, joined_on: str):
        joined_at = parse_join_date_argument(joined_on)

        if joined_at is None:
            await interaction.response.send_message("Use a date like `2025-01-14`.", ephemeral=True)
            return

        if joined_at.date() > dt.datetime.now(dt.timezone.utc).date():
            await interaction.response.send_message("Join date cannot be in the future.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        member, error = await resolve_current_clan_member(player)

        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        store.set_member_join_date(
            member["tag"],
            member.get("name", "Unknown"),
            joined_at,
            interaction.user.id,
        )
        await interaction.followup.send(
            (
                f"Known join date set for {member.get('name', 'Unknown')} `{member['tag']}`: "
                f"`{joined_at.date().isoformat()}`.\n"
                "`/war_stats`, `/last_war_bottom`, `/show_stats`, and `/show` will display this as joined date."
            ),
            ephemeral=True,
        )

    @bot.tree.command(name="clear_join_date", description="Clear a manually known clan join date.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(player="Current clan member IGN or player tag")
    async def clear_join_date(interaction: discord.Interaction, player: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        member, error = await resolve_current_clan_member(player)

        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        removed = store.clear_member_join_date(member["tag"])

        if removed is None:
            await interaction.followup.send(
                f"No known join date was set for {member.get('name', 'Unknown')} `{member['tag']}`.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Known join date cleared for {member.get('name', 'Unknown')} `{member['tag']}`.",
            ephemeral=True,
        )

    @bot.tree.command(name="sync_join_dates", description="Seed missing known join dates from the current roster.")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_join_dates(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            inserted, joined_at, source = await asyncio.to_thread(
                sync_roster_join_dates,
                store,
                clash,
                settings.clan_tag,
                dt.datetime.now(dt.timezone.utc),
            )
        except ClashApiError:
            await interaction.followup.send("The Clash Royale API is unavailable. Try again later.", ephemeral=True)
            return

        detail = (
            "baseline current roster"
            if source == JOIN_DATE_BASELINE_SOURCE
            else "newly observed current roster members"
        )
        await interaction.followup.send(
            f"Join-date sync added `{inserted}` missing dates for {detail} using `{joined_at.date().isoformat()}`.",
            ephemeral=True,
        )

    @bot.tree.command(name="war_config", description="Show Clan War stat settings.")
    @app_commands.checks.has_permissions(administrator=True)
    async def war_config(interaction: discord.Interaction):
        await interaction.response.send_message(
            (
                f"Kick suggestion threshold: `{current_kick_threshold():,}` war fame\n"
                f"Promotion suggestion threshold: `{current_promotion_threshold():,}` average war fame\n"
                f"Rolling window: `{ROLLING_WAR_DAYS}` days\n"
                f"Leaderboard eligibility: `{MIN_LEADERBOARD_WARS}+` full completed wars and `{MIN_LEADERBOARD_DAYS}+` days joined/seen\n"
                f"Promotion eligibility: `{MIN_PROMOTION_WARS}+` full completed wars and `{MIN_LEADERBOARD_DAYS}+` days joined/seen\n"
                "Join date note: Clash Royale does not expose true join date. "
                "The bot auto-seeds current members to 2026-05-04 once, then tracks new roster appearances weekly. "
                "Use `/set_join_date` for better manually known dates."
            ),
            ephemeral=True,
        )

    @bot.tree.command(name="me", description="Show your linked Clash Royale account.")
    async def me(interaction: discord.Interaction):
        link = store.get_link_by_discord_id(interaction.user.id)

        if link is None:
            await interaction.response.send_message("You are not verified yet. Run `/verify <player_tag>`.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"You are linked to {link['player_name']} `{link['player_tag']}`.",
            ephemeral=True,
        )

    @bot.tree.command(name="verify", description="Get a code to post in Clash Royale clan chat.")
    @app_commands.describe(player_tag="Your Clash Royale player tag")
    async def verify(interaction: discord.Interaction, player_tag: str):
        normalized_tag = normalize_tag(player_tag)

        if not normalized_tag:
            await interaction.response.send_message("Enter a valid Clash Royale player tag.", ephemeral=True)
            return

        if store.get_link_by_discord_id(interaction.user.id):
            await interaction.response.send_message("You are already verified.", ephemeral=True)
            return

        if store.get_link_by_player_tag(normalized_tag):
            await interaction.response.send_message("That player tag is already linked.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            player = await asyncio.to_thread(clash.get_player, normalized_tag)
        except ClashNotFound:
            await interaction.followup.send("That player tag does not exist.", ephemeral=True)
            return
        except ClashApiError:
            await interaction.followup.send("The Clash Royale API is unavailable. Try again later.", ephemeral=True)
            return

        clan_tag, clan_name = player_clan(player)

        if settings.clan_tag and clan_tag != settings.clan_tag:
            await interaction.followup.send("That player is not currently in the configured clan.", ephemeral=True)
            return

        if current_auto_verification_enabled():
            if not isinstance(interaction.user, discord.Member):
                await interaction.followup.send("Auto verification can only run inside the server.", ephemeral=True)
                return

            store.approve_direct_verification(
                interaction.user.id,
                interaction.user.id,
                discord_name(interaction.user),
                player["tag"],
                player["name"],
                clan_tag,
                clan_name,
            )
            role_note = await add_verified_role(interaction, interaction.user)
            clan_role_note = await add_clash_status_role(interaction, interaction.user, player)
            nickname_note = await set_member_nickname(interaction.user, player["name"])
            announcement_note = await announce_auto_verification(interaction, player, clan_tag, clan_name)
            message = f"Auto confirmed {interaction.user.mention} as {player['name']} `{player['tag']}`."

            if role_note:
                message += f"\n{role_note}"

            if clan_role_note:
                message += f"\n{clan_role_note}"

            if nickname_note:
                message += f"\n{nickname_note}"

            if announcement_note:
                message += f"\n{announcement_note}"

            await interaction.followup.send(message, ephemeral=True)
            return

        code = make_code()
        expires_at = store.create_challenge(
            interaction.user.id,
            discord_name(interaction.user),
            player["tag"],
            player["name"],
            code,
            settings.verification_ttl_minutes,
        )
        message = (
            f"Post this exact code in Clash Royale clan chat: `{code}`\n"
            "Then ask a leader to run `/confirm_verification` after they see it.\n"
            f"Player: {player['name']} `{player['tag']}`"
        )

        if clan_name:
            message += f"\nClan: {clan_name} `{clan_tag}`"

        announcement_note = await announce_verification_challenge(interaction, player, code, expires_at)

        if announcement_note:
            message += f"\n{announcement_note}"

        message += f"\nExpires: `{expires_at}`"
        await interaction.followup.send(message, ephemeral=True)

    @bot.tree.command(name="war_stats", description="Post current Clan War stats for the configured clan.")
    async def war_stats(interaction: discord.Interaction):
        if not settings.clan_tag:
            await interaction.response.send_message("No clan tag is configured for this bot.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=False)

        try:
            race, members, race_log = await asyncio.gather(
                asyncio.to_thread(clash.get_current_river_race, settings.clan_tag),
                asyncio.to_thread(clash.get_clan_members, settings.clan_tag),
                asyncio.to_thread(clash.get_river_race_log, settings.clan_tag, RIVER_RACE_LOG_LIMIT),
            )
        except ClashNotFound:
            await interaction.followup.send("The configured clan tag was not found.", ephemeral=True)
            return
        except ClashApiError:
            await interaction.followup.send("The Clash Royale API is unavailable. Try again later.", ephemeral=True)
            return

        now = dt.datetime.now(dt.timezone.utc)
        presence_map = await asyncio.to_thread(
            refresh_war_presence,
            store,
            settings.clan_tag,
            race,
            members,
            race_log,
            now,
        )
        embed = build_enhanced_war_stats_embed(
            race,
            members,
            race_log,
            presence_map,
            current_kick_threshold(),
            current_promotion_threshold(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @bot.tree.command(name="last_war_bottom", description="Post players ranked 41+ in the last completed war.")
    async def last_war_bottom(interaction: discord.Interaction):
        if not settings.clan_tag:
            await interaction.response.send_message("No clan tag is configured for this bot.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=False)

        try:
            race, members, race_log = await asyncio.gather(
                asyncio.to_thread(clash.get_current_river_race, settings.clan_tag),
                asyncio.to_thread(clash.get_clan_members, settings.clan_tag),
                asyncio.to_thread(clash.get_river_race_log, settings.clan_tag, RIVER_RACE_LOG_LIMIT),
            )
        except ClashNotFound:
            await interaction.followup.send("The configured clan tag was not found.", ephemeral=True)
            return
        except ClashApiError:
            await interaction.followup.send("The Clash Royale API is unavailable. Try again later.", ephemeral=True)
            return

        now = dt.datetime.now(dt.timezone.utc)
        presence_map = await asyncio.to_thread(
            refresh_war_presence,
            store,
            settings.clan_tag,
            race,
            members,
            race_log,
            now,
        )
        embed = build_last_war_bottom_embed(
            race,
            members,
            race_log,
            presence_map,
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    async def send_show_stats(interaction: discord.Interaction,
                              player: Optional[str] = None,
                              member: Optional[discord.Member] = None):
        """Send one clan member's war stats."""
        if not settings.clan_tag:
            await interaction.response.send_message("No clan tag is configured for this bot.", ephemeral=True)
            return

        player_query = (player or "").strip()
        linked_tag = None
        linked_name = None

        if member is not None:
            link = store.get_link_by_discord_id(member.id)

            if link is None:
                await interaction.response.send_message(f"{member.mention} is not verified yet.", ephemeral=True)
                return

            linked_tag = link["player_tag"]
            linked_name = link["player_name"]
        elif player_query:
            mention_id = discord_id_from_mention(player_query)

            if mention_id is not None:
                link = store.get_link_by_discord_id(mention_id)

                if link is None:
                    await interaction.response.send_message(f"<@{mention_id}> is not verified yet.", ephemeral=True)
                    return

                linked_tag = link["player_tag"]
                linked_name = link["player_name"]
        else:
            link = store.get_link_by_discord_id(interaction.user.id)

            if link is None:
                await interaction.response.send_message(
                    "Use `/show player:DaddyRizz` or `/show member:@someone`. "
                    "If you verify first, `/show` will show your own stats.",
                    ephemeral=True,
                )
                return

            linked_tag = link["player_tag"]
            linked_name = link["player_name"]

        await interaction.response.defer(thinking=True, ephemeral=False)

        try:
            race, members, race_log = await asyncio.gather(
                asyncio.to_thread(clash.get_current_river_race, settings.clan_tag),
                asyncio.to_thread(clash.get_clan_members, settings.clan_tag),
                asyncio.to_thread(clash.get_river_race_log, settings.clan_tag, RIVER_RACE_LOG_LIMIT),
            )
        except ClashNotFound:
            await interaction.followup.send("The configured clan tag was not found.", ephemeral=True)
            return
        except ClashApiError:
            await interaction.followup.send("The Clash Royale API is unavailable. Try again later.", ephemeral=True)
            return

        now = dt.datetime.now(dt.timezone.utc)
        cutoff = now - dt.timedelta(days=ROLLING_WAR_DAYS)
        historical_stats, _ = collect_completed_war_stats(race_log, (race.get("clan") or {}).get("tag"), cutoff)
        players_by_tag = war_player_index(members, race, historical_stats)

        if linked_tag:
            target = players_by_tag.get(linked_tag) or {"tag": linked_tag, "name": linked_name or "Unknown", "role": "unknown"}
        else:
            target, error = resolve_war_player(player_query, players_by_tag)

            if error:
                await interaction.followup.send(error, ephemeral=True)
                return

        presence_map = await asyncio.to_thread(
            refresh_war_presence,
            store,
            settings.clan_tag,
            race,
            members,
            race_log,
            now,
        )
        embed = build_player_war_stats_embed(
            target,
            race,
            members,
            race_log,
            presence_map,
            current_kick_threshold(),
            current_promotion_threshold(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @bot.tree.command(name="show_stats", description="Show one clan member's war stats.")
    @app_commands.describe(player="IGN or player tag, for example DaddyRizz")
    @app_commands.describe(member="Verified Discord member to look up")
    async def show_stats(interaction: discord.Interaction,
                         player: Optional[str] = None,
                         member: Optional[discord.Member] = None):
        await send_show_stats(interaction, player, member)

    @bot.tree.command(name="show", description="Show one clan member's war stats.")
    @app_commands.describe(player="IGN or player tag, for example DaddyRizz")
    @app_commands.describe(member="Verified Discord member to look up")
    async def show(interaction: discord.Interaction,
                   player: Optional[str] = None,
                   member: Optional[discord.Member] = None):
        await send_show_stats(interaction, player, member)

    @bot.tree.command(name="remove_verification", description="Remove a member's linked Clash Royale verification.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Discord member whose verification should be removed")
    async def remove_verification(interaction: discord.Interaction, member: discord.Member):
        link = store.remove_link_by_discord_id(member.id)
        role_note = await remove_verified_role(interaction, member)
        clan_role_notes = await remove_clash_status_roles(interaction, member)

        if link is None:
            message = f"No linked Clash Royale account was found for {member.mention}."
        else:
            message = f"Removed verification for {member.mention}: {link['player_name']} `{link['player_tag']}`."

        if role_note:
            message += f"\n{role_note}"

        if clan_role_notes:
            message += "\n" + "\n".join(clan_role_notes)

        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name="confirm_verification", description="Leader confirmation after seeing a code in clan chat.")
    @app_commands.check(can_confirm_verification)
    @app_commands.describe(member="Discord member who posted the code")
    @app_commands.describe(player_tag="Optional player tag if the member has more than one pending request")
    async def confirm_verification(interaction: discord.Interaction,
                                   member: discord.Member,
                                   player_tag: Optional[str] = None):
        await interaction.response.defer(thinking=True, ephemeral=True)
        normalized_tag = normalize_tag(player_tag)
        challenge = (
            store.get_pending_challenge(member.id, normalized_tag)
            if normalized_tag
            else store.get_pending_challenge_for_discord_id(member.id)
        )

        if challenge is None:
            if not normalized_tag:
                await interaction.followup.send(
                    "No active verification challenge found. "
                    "If you are using an expired leader-channel request, rerun with the player tag.",
                    ephemeral=True,
                )
                return

            player_tag_to_verify = normalized_tag
            direct_verification = True
        else:
            player_tag_to_verify = challenge["player_tag"]
            direct_verification = False

        try:
            player = await asyncio.to_thread(clash.get_player, player_tag_to_verify)
        except ClashNotFound:
            await interaction.followup.send("That player tag does not exist.", ephemeral=True)
            return
        except ClashApiError:
            await interaction.followup.send("The Clash Royale API is unavailable. Try again later.", ephemeral=True)
            return

        clan_tag, clan_name = player_clan(player)

        if settings.clan_tag and clan_tag != settings.clan_tag:
            await interaction.followup.send("That player is not currently in the configured clan.", ephemeral=True)
            return

        existing_player_link = store.get_link_by_player_tag(player["tag"])

        if existing_player_link and existing_player_link["discord_id"] != member.id:
            await interaction.followup.send(
                f"That player tag is already linked to <@{existing_player_link['discord_id']}>.",
                ephemeral=True,
            )
            return

        if direct_verification:
            store.approve_direct_verification(
                interaction.user.id,
                member.id,
                discord_name(member),
                player["tag"],
                player["name"],
                clan_tag,
                clan_name,
            )
        else:
            store.approve_challenge(
                challenge["id"],
                interaction.user.id,
                member.id,
                discord_name(member),
                player["tag"],
                player["name"],
                clan_tag,
                clan_name,
            )

        role_note = await add_verified_role(interaction, member)
        clan_role_note = await add_clash_status_role(interaction, member, player)
        nickname_note = await set_member_nickname(member, player["name"])

        message = f"Verified {member.mention} as {player['name']} `{player['tag']}`."

        if direct_verification:
            message += "\nUsed admin direct verification because no active challenge was found."

        if role_note:
            message += f"\n{role_note}"

        if clan_role_note:
            message += f"\n{clan_role_note}"

        if nickname_note:
            message += f"\n{nickname_note}"

        await interaction.followup.send(message, ephemeral=True)

    @confirm_verification.error
    async def confirm_verification_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await send_ephemeral(interaction, "Only server admins or members with the Elder role can confirm verifications.")
        else:
            LOG.exception("Unexpected command error", exc_info=error)
            await send_ephemeral(interaction, "Unexpected error.")

    @set_verified_role.error
    @set_elder_role.error
    @set_coleader_role.error
    @set_verification_channel.error
    @set_auto_verification.error
    @set_kick_threshold.error
    @set_promotion_threshold.error
    @set_join_date.error
    @clear_join_date.error
    @sync_join_dates.error
    @war_config.error
    @verification_config.error
    @remove_verification.error
    async def verification_admin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await send_ephemeral(interaction, "Only server admins can manage verification settings.")
        else:
            LOG.exception("Unexpected command error", exc_info=error)
            await send_ephemeral(interaction, "Unexpected error.")

    return bot


def main():
    """Run the micro bot."""
    logging.basicConfig(level=logging.INFO)
    bot = build_bot()
    bot.run(bot.settings.discord_token)


if __name__ == "__main__":
    main()
