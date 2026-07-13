"""Tiny Discord bot entry point."""

import asyncio
import datetime as dt
import logging
import secrets
import string
from typing import Any, Optional

import discord
from discord import app_commands

from microbot.clash_api import ClashApiError, ClashClient, ClashNotFound
from microbot.config import Settings, load_settings, normalize_tag
from microbot.storage import Store


LOG = logging.getLogger("microbot")
DEFAULT_VERIFICATION_CHANNEL_NAME = "verification-confirmation"
DEFAULT_KICK_THRESHOLD = 2000
DEFAULT_PROMOTION_THRESHOLD = 3000
MIN_LEADERBOARD_WARS = 2
MIN_LEADERBOARD_DAYS = 14
MIN_PROMOTION_WARS = 3
RIVER_RACE_LOG_LIMIT = 10
ROLLING_WAR_DAYS = 35


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
    embed.add_field(
        name="Summary",
        value=(
            f"Fame: **{fame:,}**\n"
            f"Decks today: **{decks_today}/200**\n"
            f"Current roster remaining: **{remaining_roster_decks}/{roster_capacity}**\n"
            f"Decks total this race: **{decks_total}**\n"
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
            f"{int_value(participant.get('decksUsedToday'))}/4 today"
        )

    embed.add_field(
        name="Top Contributors",
        value=clip_text("\n".join(top_lines) or "No war battles logged yet."),
        inline=False,
    )

    needs_decks.sort(key=lambda item: (item[0], str(item[1]).lower()))
    needs_decks_lines = [
        f"{format_name(name)} - {used}/4"
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
            f"{int_value(race_clan.get('fame')):,} fame, {clan_decks_today} decks today"
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
                {"name": participant.get("name", "Unknown"), "scores": []},
            )
            entry["name"] = participant.get("name", entry["name"])
            entry["scores"].append(int_value(participant.get("fame")))

    return player_stats, race_dates


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


def score_line(name: str,
               current_fame: int,
               average_fame: Optional[float],
               race_count: int,
               first_seen_at: Optional[dt.datetime],
               now: dt.datetime,
               reason: str) -> str:
    """Format a compact member war score line."""
    average_text = f"{average_fame:,.0f}" if average_fame is not None else "n/a"
    return (
        f"{format_name(name)} - {current_fame:,} current, "
        f"{average_text} avg/{race_count} wars, "
        f"seen {short_date(first_seen_at)} ({days_ago_label(first_seen_at, now)}): {reason}"
    )


def add_line_fields(embed: discord.Embed, title: str, lines: list[str], empty_text: str):
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
        field_title = title if index == 1 else f"{title} ({index})"
        embed.add_field(name=field_title, value="\n".join(chunk), inline=False)


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

    current_fame_total = sum(int_value(participant.get("fame")) for participant in current_participants)
    decks_today = sum(int_value(participant.get("decksUsedToday")) for participant in current_participants)
    decks_total = sum(int_value(participant.get("decksUsed")) for participant in current_participants)
    period_index = int_value(race.get("periodIndex"))
    current_week_day = (period_index % 7) + 1

    embed = discord.Embed(
        title=f"{current_clan.get('name', 'Clan')} War Stats",
        description=f"Current race plus completed wars since {short_date(cutoff)}.",
        color=discord.Color.blue(),
        timestamp=now,
    )
    embed.add_field(
        name="Current War",
        value=(
            f"Fame: **{current_fame_total:,}**\n"
            f"Decks today: **{decks_today}/200**\n"
            f"Decks total: **{decks_total}**\n"
            f"War day estimate: **{current_week_day}/7**\n"
            f"Kick threshold: **{kick_threshold:,} war fame**\n"
            f"Promotion threshold: **{promotion_threshold:,} avg war fame**"
        ),
        inline=False,
    )

    rolling_rows = []
    promotion_rows = []
    suggested_rows = []
    review_rows = []

    for member in members:
        player_tag = member.get("tag")

        if not player_tag:
            continue

        player_name = member.get("name", "Unknown")
        participant = current_by_tag.get(player_tag, {})
        current_fame = int_value(participant.get("fame"))
        history = historical_stats.get(player_tag, {})
        scores = history.get("scores", [])
        race_count = len(scores)
        average_fame = (sum(scores) / race_count) if race_count else None
        presence = presence_map.get(player_tag)
        first_seen_at = parse_iso_datetime(presence["first_seen_at"]) if presence else None
        has_leaderboard_tenure = has_min_tenure(first_seen_at, now, MIN_LEADERBOARD_DAYS)
        tracked_after_race_start = first_seen_at is None or first_seen_at > race_start + dt.timedelta(hours=6)
        tracked_from_race_start = first_seen_at is not None and first_seen_at <= race_start + dt.timedelta(hours=6)
        low_current = current_fame < kick_threshold
        low_average = average_fame is not None and race_count >= 2 and average_fame < kick_threshold
        good_average = average_fame is not None and race_count >= 2 and average_fame >= kick_threshold

        if average_fame is not None and race_count >= MIN_LEADERBOARD_WARS and has_leaderboard_tenure:
            rolling_rows.append((average_fame, race_count, player_name, current_fame, first_seen_at))

        if (average_fame is not None
                and average_fame >= promotion_threshold
                and race_count >= MIN_PROMOTION_WARS
                and has_leaderboard_tenure
                and current_fame >= kick_threshold):
            promotion_rows.append((average_fame, race_count, player_name, current_fame, first_seen_at))

        if current_fame == 0 and tracked_after_race_start:
            review_rows.append(
                score_line(player_name, current_fame, average_fame, race_count, first_seen_at, now, "newly tracked this war; do not count this war")
            )
        elif low_average:
            suggested_rows.append(
                score_line(player_name, current_fame, average_fame, race_count, first_seen_at, now, "rolling average below threshold")
            )
        elif low_current and average_fame is not None and race_count < MIN_LEADERBOARD_WARS and average_fame >= kick_threshold:
            review_rows.append(
                score_line(player_name, current_fame, average_fame, race_count, first_seen_at, now, "low current, but history is too small")
            )
        elif low_current and tracked_from_race_start and not good_average:
            suggested_rows.append(
                score_line(player_name, current_fame, average_fame, race_count, first_seen_at, now, "below threshold and tracked from war start")
            )
        elif low_current and tracked_after_race_start and current_fame > 0:
            review_rows.append(
                score_line(player_name, current_fame, average_fame, race_count, first_seen_at, now, "low current, but tracked after war start")
            )
        elif low_current and good_average:
            review_rows.append(
                score_line(player_name, current_fame, average_fame, race_count, first_seen_at, now, "low current, but good rolling average")
            )

    rolling_rows.sort(key=lambda row: (row[0], row[1], row[2].lower()), reverse=True)
    rolling_lines = [
        (
            f"{index}. {format_name(name)} - {average:,.0f} avg/{race_count} wars, "
            f"{current_fame:,} current, seen {short_date(first_seen)}"
        )
        for index, (average, race_count, name, current_fame, first_seen) in enumerate(rolling_rows[:10], 1)
    ]
    embed.add_field(
        name=f"Rolling {ROLLING_WAR_DAYS}-Day Leaders",
        value=clip_text(
            "\n".join(rolling_lines)
            or f"No eligible members yet. Requires {MIN_LEADERBOARD_WARS}+ completed wars and {MIN_LEADERBOARD_DAYS}+ days first-seen."
        ),
        inline=False,
    )

    promotion_rows.sort(key=lambda row: (row[0], row[1], row[2].lower()), reverse=True)
    promotion_lines = [
        (
            f"{format_name(name)} - {average:,.0f} avg/{race_count} wars, "
            f"{current_fame:,} current, seen {short_date(first_seen)}"
        )
        for average, race_count, name, current_fame, first_seen in promotion_rows
    ]
    add_line_fields(
        embed,
        "Suggested Promotions",
        promotion_lines,
        f"No promotion suggestions. Requires {promotion_threshold:,}+ average, {MIN_PROMOTION_WARS}+ wars, and {MIN_LEADERBOARD_DAYS}+ days first-seen.",
    )

    add_line_fields(
        embed,
        "Suggested Kicks",
        suggested_rows,
        "No kick suggestions at the current threshold.",
    )

    add_line_fields(
        embed,
        "Review / Likely Excuse",
        review_rows,
        "No low-score exceptions detected.",
    )

    completed_count = len(completed_race_dates)
    embed.set_footer(
        text=(
            f"{completed_count} completed wars in window. "
            "First seen is tracked by bot/API observations; Clash API does not expose true join date."
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

    def current_verification_channel_id() -> Optional[int]:
        """Return the configured verification review channel."""
        return store.get_verification_channel_id()

    def current_kick_threshold() -> int:
        """Return the configured minimum war fame for kick suggestions."""
        return store.get_kick_threshold() or DEFAULT_KICK_THRESHOLD

    def current_promotion_threshold() -> int:
        """Return the configured average war fame for promotion suggestions."""
        return store.get_promotion_threshold() or DEFAULT_PROMOTION_THRESHOLD

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

        try:
            await member.add_roles(role, reason="Clash Royale clan verification")
        except discord.Forbidden:
            return "The account is verified, but I do not have permission to assign the verified role."
        except discord.HTTPException:
            return "The account is verified, but Discord rejected the role assignment."

        return f"Assigned {role.mention}."

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
                f"After you see the code in clan chat, run `/confirm_verification member:{interaction.user.mention}`.\n"
                f"Fallback with tag: `/confirm_verification member:{interaction.user.mention} player_tag:{player['tag']}`"
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

        notes = []
        bot_member = interaction.guild.me if interaction.guild else None

        if bot_member and bot_member.top_role <= role:
            notes.append("Move the bot's role above this role in Server Settings > Roles so it can assign it.")

        if not interaction.app_permissions.manage_roles:
            notes.append("The bot also needs the Manage Roles permission.")

        store.set_verified_role_id(role.id)
        message = f"Verified role set to {role.mention}."

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

    @bot.tree.command(name="verification_config", description="Show verification role configuration.")
    @app_commands.checks.has_permissions(administrator=True)
    async def verification_config(interaction: discord.Interaction):
        role_id = current_verified_role_id()
        channel_id = current_verification_channel_id()
        lines = []

        if role_id is None:
            lines.append("Verified role: not configured")
        else:
            role = interaction.guild.get_role(role_id) if interaction.guild else None
            role_label = role.mention if role else f"`{role_id}` (not found)"
            lines.append(f"Verified role: {role_label}")

        if channel_id is None:
            lines.append("Leader verification channel: not configured")
        else:
            channel = bot.get_channel(channel_id)
            channel_label = channel.mention if channel else f"`{channel_id}` (not found)"
            lines.append(f"Leader verification channel: {channel_label}")

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

    @bot.tree.command(name="war_config", description="Show Clan War stat settings.")
    @app_commands.checks.has_permissions(administrator=True)
    async def war_config(interaction: discord.Interaction):
        await interaction.response.send_message(
            (
                f"Kick suggestion threshold: `{current_kick_threshold():,}` war fame\n"
                f"Promotion suggestion threshold: `{current_promotion_threshold():,}` average war fame\n"
                f"Rolling window: `{ROLLING_WAR_DAYS}` days\n"
                f"Leaderboard eligibility: `{MIN_LEADERBOARD_WARS}+` completed wars and `{MIN_LEADERBOARD_DAYS}+` days first-seen\n"
                f"Promotion eligibility: `{MIN_PROMOTION_WARS}+` completed wars and `{MIN_LEADERBOARD_DAYS}+` days first-seen\n"
                "Join date note: Clash Royale does not expose true join date; this bot shows first seen."
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
        record_war_presence(store, settings.clan_tag, race, members, race_log, now)
        presence_map = store.get_member_presence_map()
        embed = build_enhanced_war_stats_embed(
            race,
            members,
            race_log,
            presence_map,
            current_kick_threshold(),
            current_promotion_threshold(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @bot.tree.command(name="remove_verification", description="Remove a member's linked Clash Royale verification.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Discord member whose verification should be removed")
    async def remove_verification(interaction: discord.Interaction, member: discord.Member):
        link = store.remove_link_by_discord_id(member.id)
        role_note = await remove_verified_role(interaction, member)

        if link is None:
            message = f"No linked Clash Royale account was found for {member.mention}."
        else:
            message = f"Removed verification for {member.mention}: {link['player_name']} `{link['player_tag']}`."

        if role_note:
            message += f"\n{role_note}"

        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name="confirm_verification", description="Leader confirmation after seeing a code in clan chat.")
    @app_commands.checks.has_permissions(administrator=True)
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
            await interaction.followup.send("No active verification challenge found.", ephemeral=True)
            return

        try:
            player = await asyncio.to_thread(clash.get_player, challenge["player_tag"])
        except ClashApiError:
            await interaction.followup.send("The Clash Royale API is unavailable. Try again later.", ephemeral=True)
            return

        clan_tag, clan_name = player_clan(player)
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
        nickname_note = await set_member_nickname(member, player["name"])

        message = f"Verified {member.mention} as {player['name']} `{player['tag']}`."

        if role_note:
            message += f"\n{role_note}"

        if nickname_note:
            message += f"\n{nickname_note}"

        await interaction.followup.send(message, ephemeral=True)

    @confirm_verification.error
    async def confirm_verification_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await send_ephemeral(interaction, "Only server admins can confirm verifications.")
        else:
            LOG.exception("Unexpected command error", exc_info=error)
            await send_ephemeral(interaction, "Unexpected error.")

    @set_verified_role.error
    @set_verification_channel.error
    @set_kick_threshold.error
    @set_promotion_threshold.error
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
