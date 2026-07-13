"""Small stdlib Clash Royale API client."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from microbot.config import normalize_tag


class ClashApiError(RuntimeError):
    """Raised when the Clash Royale API request fails."""


class ClashNotFound(ClashApiError):
    """Raised when a Clash Royale resource does not exist."""


class ClashClient:
    """Minimal Clash Royale API client."""

    base_url = "https://api.clashroyale.com/v1"

    def __init__(self, token: str):
        self.token = token

    def _get(self, path: str) -> Dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={
                "Accept": "application/json",
                "authorization": f"Bearer {self.token}",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ClashNotFound(path) from exc

            raise ClashApiError(f"Clash API returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ClashApiError(str(exc)) from exc

    def get_player(self, tag: str) -> Dict[str, Any]:
        """Fetch a player by tag."""
        normalized_tag = normalize_tag(tag)
        encoded_tag = urllib.parse.quote(normalized_tag, safe="")
        return self._get(f"/players/{encoded_tag}")

    def get_clan(self, tag: str) -> Dict[str, Any]:
        """Fetch a clan by tag."""
        normalized_tag = normalize_tag(tag)
        encoded_tag = urllib.parse.quote(normalized_tag, safe="")
        return self._get(f"/clans/{encoded_tag}")

    def get_clan_members(self, tag: str) -> Dict[str, Any]:
        """Fetch members for a clan."""
        normalized_tag = normalize_tag(tag)
        encoded_tag = urllib.parse.quote(normalized_tag, safe="")
        return self._get(f"/clans/{encoded_tag}/members")

    def get_current_river_race(self, tag: str) -> Dict[str, Any]:
        """Fetch the current river race for a clan."""
        normalized_tag = normalize_tag(tag)
        encoded_tag = urllib.parse.quote(normalized_tag, safe="")
        return self._get(f"/clans/{encoded_tag}/currentriverrace")

    def get_river_race_log(self, tag: str, limit: int = 10) -> Dict[str, Any]:
        """Fetch recent completed river races for a clan."""
        normalized_tag = normalize_tag(tag)
        encoded_tag = urllib.parse.quote(normalized_tag, safe="")
        query = urllib.parse.urlencode({"limit": limit})
        return self._get(f"/clans/{encoded_tag}/riverracelog?{query}")
