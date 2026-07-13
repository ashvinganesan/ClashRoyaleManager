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
                """
            )

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

    def get_link_by_discord_id(self, discord_id: int) -> Optional[sqlite3.Row]:
        """Return a linked account by Discord id."""
        with self.connect() as connection:
            return connection.execute("SELECT * FROM linked_accounts WHERE discord_id = ?", (discord_id,)).fetchone()

    def get_link_by_player_tag(self, player_tag: str) -> Optional[sqlite3.Row]:
        """Return a linked account by player tag."""
        with self.connect() as connection:
            return connection.execute("SELECT * FROM linked_accounts WHERE player_tag = ?", (player_tag,)).fetchone()

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
