"""SQLite storage for the micro bot."""

import datetime as dt
import os
import sqlite3
from typing import Optional


def utc_now() -> dt.datetime:
    """Return current UTC time."""
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    """Serialize a datetime."""
    return value.astimezone(dt.timezone.utc).isoformat()


class Store:
    """Small SQLite store."""

    def __init__(self, path: str):
        self.path = path
        directory = os.path.dirname(path)

        if directory:
            os.makedirs(directory, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """Open a SQLite connection."""
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self):
        """Create tables."""
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS verification_challenges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_id INTEGER NOT NULL,
                    discord_name TEXT NOT NULL,
                    player_tag TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    challenge_code TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    reviewed_by_discord_id INTEGER,
                    reviewed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_verification_status
                    ON verification_challenges(status, expires_at);

                CREATE TABLE IF NOT EXISTS linked_accounts (
                    discord_id INTEGER PRIMARY KEY,
                    discord_name TEXT NOT NULL,
                    player_tag TEXT NOT NULL UNIQUE,
                    player_name TEXT NOT NULL,
                    clan_tag TEXT,
                    clan_name TEXT,
                    verified_at TEXT NOT NULL,
                    verified_by_discord_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clan_member_presence (
                    player_tag TEXT PRIMARY KEY,
                    player_name TEXT NOT NULL,
                    clan_tag TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    first_seen_source TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS member_join_dates (
                    player_tag TEXT PRIMARY KEY,
                    player_name TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    set_by_discord_id INTEGER,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def set_setting(self, key: str, value: str):
        """Persist a bot setting."""
        now = iso(utc_now())

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO bot_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )

    def get_setting(self, key: str) -> Optional[str]:
        """Read a bot setting."""
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)).fetchone()

        return None if row is None else row["value"]

    def set_verified_role_id(self, role_id: int):
        """Persist the Discord role id assigned after verification."""
        self.set_setting("verified_role_id", str(role_id))

    def get_verified_role_id(self) -> Optional[int]:
        """Return the configured Discord verification role id."""
        value = self.get_setting("verified_role_id")

        if not value:
            return None

        try:
            return int(value)
        except ValueError:
            return None

    def set_elder_role_id(self, role_id: int):
        """Persist the Discord role id assigned to in-game elders."""
        self.set_setting("elder_role_id", str(role_id))

    def get_elder_role_id(self) -> Optional[int]:
        """Return the configured Discord elder role id."""
        value = self.get_setting("elder_role_id")

        if not value:
            return None

        try:
            return int(value)
        except ValueError:
            return None

    def set_coleader_role_id(self, role_id: int):
        """Persist the Discord role id assigned to in-game co-leaders/leaders."""
        self.set_setting("coleader_role_id", str(role_id))

    def get_coleader_role_id(self) -> Optional[int]:
        """Return the configured Discord co-leader role id."""
        value = self.get_setting("coleader_role_id")

        if not value:
            return None

        try:
            return int(value)
        except ValueError:
            return None

    def set_verification_channel_id(self, channel_id: int):
        """Persist the Discord channel id used for verification review."""
        self.set_setting("verification_channel_id", str(channel_id))

    def get_verification_channel_id(self) -> Optional[int]:
        """Return the configured Discord verification review channel id."""
        value = self.get_setting("verification_channel_id")

        if not value:
            return None

        try:
            return int(value)
        except ValueError:
            return None

    def set_auto_verification_enabled(self, enabled: bool):
        """Persist whether /verify should immediately link current clan tags."""
        self.set_setting("auto_verification_enabled", "1" if enabled else "0")

    def get_auto_verification_enabled(self) -> bool:
        """Return whether /verify should immediately link current clan tags."""
        return self.get_setting("auto_verification_enabled") == "1"

    def set_kick_threshold(self, min_fame: int):
        """Persist the minimum war fame used for kick suggestions."""
        self.set_setting("kick_threshold", str(min_fame))

    def get_kick_threshold(self) -> Optional[int]:
        """Return the configured minimum war fame used for kick suggestions."""
        value = self.get_setting("kick_threshold")

        if not value:
            return None

        try:
            return int(value)
        except ValueError:
            return None

    def set_promotion_threshold(self, min_average_fame: int):
        """Persist the minimum average war fame used for promotion suggestions."""
        self.set_setting("promotion_threshold", str(min_average_fame))

    def get_promotion_threshold(self) -> Optional[int]:
        """Return the configured minimum average war fame used for promotion suggestions."""
        value = self.get_setting("promotion_threshold")

        if not value:
            return None

        try:
            return int(value)
        except ValueError:
            return None

    def set_member_join_date(self,
                             player_tag: str,
                             player_name: str,
                             joined_at: dt.datetime,
                             set_by_discord_id: Optional[int],
                             source: str = "manual"):
        """Persist a known clan join date."""
        now = iso(utc_now())
        joined_value = iso(joined_at)

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO member_join_dates (
                    player_tag, player_name, joined_at, source, set_by_discord_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_tag) DO UPDATE SET
                    player_name = excluded.player_name,
                    joined_at = excluded.joined_at,
                    source = excluded.source,
                    set_by_discord_id = excluded.set_by_discord_id,
                    updated_at = excluded.updated_at
                """,
                (player_tag, player_name, joined_value, source, set_by_discord_id, now),
            )

    def seed_missing_member_join_dates(self,
                                       members: list[dict],
                                       joined_at: dt.datetime,
                                       source: str) -> int:
        """Set a known clan join date for current members without one."""
        now = iso(utc_now())
        joined_value = iso(joined_at)
        inserted = 0

        with self.connect() as connection:
            for member in members:
                player_tag = member.get("tag")

                if not player_tag:
                    continue

                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO member_join_dates (
                        player_tag, player_name, joined_at, source, set_by_discord_id, updated_at
                    )
                    VALUES (?, ?, ?, ?, NULL, ?)
                    """,
                    (player_tag, member.get("name", "Unknown"), joined_value, source, now),
                )
                inserted += cursor.rowcount

        return inserted

    def clear_member_join_date(self, player_tag: str) -> Optional[sqlite3.Row]:
        """Remove a manually known clan join date."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM member_join_dates WHERE player_tag = ?",
                (player_tag,),
            ).fetchone()
            connection.execute("DELETE FROM member_join_dates WHERE player_tag = ?", (player_tag,))

        return row

    def get_member_join_date_map(self) -> dict[str, sqlite3.Row]:
        """Return manually known clan join dates keyed by player tag."""
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM member_join_dates").fetchall()

        return {row["player_tag"]: row for row in rows}

    def upsert_member_presence(self,
                               player_tag: str,
                               player_name: str,
                               clan_tag: Optional[str],
                               seen_at: dt.datetime,
                               source: str):
        """Record that a player was seen in the clan or clan war history."""
        seen_value = iso(seen_at)

        with self.connect() as connection:
            row = connection.execute(
                "SELECT first_seen_at FROM clan_member_presence WHERE player_tag = ?",
                (player_tag,),
            ).fetchone()

            if row is None:
                connection.execute(
                    """
                    INSERT INTO clan_member_presence (
                        player_tag, player_name, clan_tag, first_seen_at, last_seen_at, first_seen_source
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (player_tag, player_name, clan_tag, seen_value, seen_value, source),
                )
                return

            first_seen_at = min(row["first_seen_at"], seen_value)
            first_seen_source = source if first_seen_at == seen_value else None
            connection.execute(
                """
                UPDATE clan_member_presence
                SET player_name = ?,
                    clan_tag = ?,
                    first_seen_at = ?,
                    last_seen_at = MAX(last_seen_at, ?),
                    first_seen_source = COALESCE(?, first_seen_source)
                WHERE player_tag = ?
                """,
                (player_name, clan_tag, first_seen_at, seen_value, first_seen_source, player_tag),
            )

    def get_member_presence_map(self) -> dict[str, sqlite3.Row]:
        """Return stored clan member presence keyed by player tag."""
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM clan_member_presence").fetchall()

        return {row["player_tag"]: row for row in rows}

    def create_challenge(self,
                         discord_id: int,
                         discord_name: str,
                         player_tag: str,
                         player_name: str,
                         challenge_code: str,
                         ttl_minutes: int) -> str:
        """Create a pending challenge and return its expiry time."""
        now = utc_now()
        expires_at = now + dt.timedelta(minutes=ttl_minutes)

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE verification_challenges
                SET status = 'cancelled'
                WHERE status = 'pending' AND (discord_id = ? OR player_tag = ?)
                """,
                (discord_id, player_tag),
            )
            connection.execute(
                """
                INSERT INTO verification_challenges (
                    discord_id, discord_name, player_tag, player_name,
                    challenge_code, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (discord_id, discord_name, player_tag, player_name, challenge_code, iso(now), iso(expires_at)),
            )

        return iso(expires_at)

    def get_pending_challenge(self, discord_id: int, player_tag: str) -> Optional[sqlite3.Row]:
        """Return the newest pending challenge for a member/tag."""
        now = iso(utc_now())

        with self.connect() as connection:
            connection.execute(
                "UPDATE verification_challenges SET status = 'expired' WHERE status = 'pending' AND expires_at < ?",
                (now,),
            )
            return connection.execute(
                """
                SELECT *
                FROM verification_challenges
                WHERE discord_id = ? AND player_tag = ? AND status = 'pending' AND expires_at >= ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (discord_id, player_tag, now),
            ).fetchone()

    def get_pending_challenge_for_discord_id(self, discord_id: int) -> Optional[sqlite3.Row]:
        """Return the newest pending challenge for a member."""
        now = iso(utc_now())

        with self.connect() as connection:
            connection.execute(
                "UPDATE verification_challenges SET status = 'expired' WHERE status = 'pending' AND expires_at < ?",
                (now,),
            )
            return connection.execute(
                """
                SELECT *
                FROM verification_challenges
                WHERE discord_id = ? AND status = 'pending' AND expires_at >= ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (discord_id, now),
            ).fetchone()

    def get_link_by_discord_id(self, discord_id: int) -> Optional[sqlite3.Row]:
        """Return a linked account by Discord id."""
        with self.connect() as connection:
            return connection.execute("SELECT * FROM linked_accounts WHERE discord_id = ?", (discord_id,)).fetchone()

    def get_link_by_player_tag(self, player_tag: str) -> Optional[sqlite3.Row]:
        """Return a linked account by player tag."""
        with self.connect() as connection:
            return connection.execute("SELECT * FROM linked_accounts WHERE player_tag = ?", (player_tag,)).fetchone()

    def remove_link_by_discord_id(self, discord_id: int) -> Optional[sqlite3.Row]:
        """Remove a linked account and cancel pending challenges for a Discord id."""
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM linked_accounts WHERE discord_id = ?", (discord_id,)).fetchone()
            connection.execute("DELETE FROM linked_accounts WHERE discord_id = ?", (discord_id,))
            connection.execute(
                "UPDATE verification_challenges SET status = 'cancelled' WHERE discord_id = ? AND status = 'pending'",
                (discord_id,),
            )

        return row

    def approve_challenge(self,
                          challenge_id: int,
                          reviewer_discord_id: int,
                          discord_id: int,
                          discord_name: str,
                          player_tag: str,
                          player_name: str,
                          clan_tag: Optional[str],
                          clan_name: Optional[str]):
        """Approve a challenge and link a Discord account to a player."""
        now = iso(utc_now())

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO linked_accounts (
                    discord_id, discord_name, player_tag, player_name,
                    clan_tag, clan_name, verified_at, verified_by_discord_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(discord_id) DO UPDATE SET
                    discord_name = excluded.discord_name,
                    player_tag = excluded.player_tag,
                    player_name = excluded.player_name,
                    clan_tag = excluded.clan_tag,
                    clan_name = excluded.clan_name,
                    verified_at = excluded.verified_at,
                    verified_by_discord_id = excluded.verified_by_discord_id
                """,
                (discord_id, discord_name, player_tag, player_name, clan_tag, clan_name, now, reviewer_discord_id),
            )
            connection.execute(
                """
                UPDATE verification_challenges
                SET status = 'approved', reviewed_by_discord_id = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (reviewer_discord_id, now, challenge_id),
            )

    def approve_direct_verification(self,
                                    reviewer_discord_id: int,
                                    discord_id: int,
                                    discord_name: str,
                                    player_tag: str,
                                    player_name: str,
                                    clan_tag: Optional[str],
                                    clan_name: Optional[str]):
        """Link a Discord account to a player directly by admin action."""
        now = iso(utc_now())

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO linked_accounts (
                    discord_id, discord_name, player_tag, player_name,
                    clan_tag, clan_name, verified_at, verified_by_discord_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(discord_id) DO UPDATE SET
                    discord_name = excluded.discord_name,
                    player_tag = excluded.player_tag,
                    player_name = excluded.player_name,
                    clan_tag = excluded.clan_tag,
                    clan_name = excluded.clan_name,
                    verified_at = excluded.verified_at,
                    verified_by_discord_id = excluded.verified_by_discord_id
                """,
                (discord_id, discord_name, player_tag, player_name, clan_tag, clan_name, now, reviewer_discord_id),
            )
            connection.execute(
                """
                UPDATE verification_challenges
                SET status = 'approved',
                    reviewed_by_discord_id = ?,
                    reviewed_at = ?
                WHERE discord_id = ?
                    AND player_tag = ?
                    AND status IN ('pending', 'expired')
                """,
                (reviewer_discord_id, now, discord_id, player_tag),
            )
