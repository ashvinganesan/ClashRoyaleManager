"""Environment-backed application settings."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


_DOTENV_LOADED = False


def load_dotenv(path: Optional[Path] = None):
    """Load simple KEY=VALUE pairs from a local .env file without overriding the environment."""
    global _DOTENV_LOADED

    if _DOTENV_LOADED:
        return

    _DOTENV_LOADED = True
    env_path = path or Path(__file__).resolve().parents[2] / ".env"

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


def get_env(name: str, *, default: Optional[str] = None, required: bool = True) -> Optional[str]:
    """Read an environment variable and raise a clear error when it is required."""
    load_dotenv()
    value = os.environ.get(name, default)

    if required and (value is None or value == ""):
        raise ConfigurationError(f"Missing required environment variable: {name}")

    return value


def get_int_env(name: str, *, default: Optional[int] = None, required: bool = True) -> Optional[int]:
    """Read an integer environment variable."""
    raw_value = get_env(name, default=None if default is None else str(default), required=required)

    if raw_value in {None, ""}:
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {name} must be an integer") from exc


def get_discord_bot_token() -> str:
    """Return the Discord bot token."""
    return get_env("DISCORD_BOT_TOKEN")


def get_discord_guild_id() -> Optional[int]:
    """Return the configured Discord guild id, if one was supplied."""
    return get_int_env("DISCORD_GUILD_ID", required=False)


def get_clash_api_token() -> str:
    """Return the Clash Royale API token."""
    return get_env("CLASH_ROYALE_API_TOKEN")


@dataclass(frozen=True)
class DatabaseConfig:
    """Database connection settings."""

    host: str
    port: int
    user: str
    password: str
    database: str


def get_database_config() -> DatabaseConfig:
    """Return MySQL connection settings."""
    return DatabaseConfig(
        host=get_env("MYSQL_HOST", default="localhost", required=False),
        port=get_int_env("MYSQL_PORT", default=3306, required=False),
        user=get_env("MYSQL_USER"),
        password=get_env("MYSQL_PASSWORD"),
        database=get_env("MYSQL_DATABASE"),
    )
