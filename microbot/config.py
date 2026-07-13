"""Configuration for the micro Discord bot."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


_DOTENV_LOADED = False


def load_dotenv(path: Optional[Path] = None):
    """Load a simple .env file without overriding real environment variables."""
    global _DOTENV_LOADED

    if _DOTENV_LOADED:
        return

    _DOTENV_LOADED = True
    env_path = path or Path.cwd() / ".env"

    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if key:
            os.environ.setdefault(key, value)


def env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Read an environment variable."""
    load_dotenv()
    value = os.environ.get(name, default)

    if required and not value:
        raise ConfigError(f"Missing required environment variable: {name}")

    return value


def env_int(name: str, default: Optional[int] = None, required: bool = False) -> Optional[int]:
    """Read an integer environment variable."""
    value = env(name, None if default is None else str(default), required)

    if value in {None, ""}:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    """Micro bot settings."""

    discord_token: str
    discord_guild_id: Optional[int]
    clash_api_token: str
    clan_tag: Optional[str]
    database_path: str
    verified_role_id: Optional[int]
    verification_ttl_minutes: int
    heartbeat_path: str


def load_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings(
        discord_token=env("DISCORD_BOT_TOKEN", required=True),
        discord_guild_id=env_int("DISCORD_GUILD_ID"),
        clash_api_token=env("CLASH_ROYALE_API_TOKEN", required=True),
        clan_tag=normalize_tag(env("CLAN_TAG")),
        database_path=env("MICROBOT_DATABASE_PATH", "data/microbot.sqlite3", required=True),
        verified_role_id=env_int("DISCORD_VERIFIED_ROLE_ID"),
        verification_ttl_minutes=env_int("VERIFICATION_TTL_MINUTES", 30, required=True),
        heartbeat_path=env("MICROBOT_HEARTBEAT_PATH", "/tmp/clash-royale-microbot.heartbeat", required=True),
    )


def normalize_tag(tag: Optional[str]) -> Optional[str]:
    """Normalize Clash Royale tags to #ABC123 form."""
    if tag is None:
        return None

    cleaned = tag.strip().upper().replace("O", "0")

    if not cleaned:
        return None

    if not cleaned.startswith("#"):
        cleaned = f"#{cleaned}"

    return cleaned
