import datetime as dt
import importlib.util
import tempfile
import unittest
from pathlib import Path

from microbot.storage import Store

DISCORD_AVAILABLE = importlib.util.find_spec("discord") is not None

if DISCORD_AVAILABLE:
    from microbot.bot import JOIN_DATE_BASELINE_SETTING, sync_roster_join_dates


class FakeClashClient:
    def __init__(self, members):
        self.members = members

    def get_clan_members(self, clan_tag):
        return {"items": self.members}


@unittest.skipUnless(DISCORD_AVAILABLE, "discord.py is not installed")
class MicrobotJoinDateTests(unittest.TestCase):
    def test_sync_seeds_baseline_then_tracks_new_members(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()
            first_now = dt.datetime(2026, 7, 14, 12, tzinfo=dt.timezone.utc)
            second_now = dt.datetime(2026, 7, 21, 12, tzinfo=dt.timezone.utc)
            store.upsert_member_presence(
                "#ALPHA",
                "alphawolf143",
                "#CLAN",
                dt.datetime(2026, 5, 4, 9, tzinfo=dt.timezone.utc),
                "river race log",
            )
            store.upsert_member_presence(
                "#BETA",
                "Beta",
                "#CLAN",
                dt.datetime(2026, 6, 29, 9, tzinfo=dt.timezone.utc),
                "river race log",
            )

            inserted, source_counts = sync_roster_join_dates(
                store,
                FakeClashClient(
                    [
                        {"tag": "#ALPHA", "name": "alphawolf143"},
                        {"tag": "#BETA", "name": "Beta"},
                    ]
                ),
                "#CLAN",
                first_now,
            )
            join_dates = store.get_member_join_date_map()

            self.assertEqual(inserted, 2)
            self.assertEqual(source_counts, {"auto-baseline": 1, "auto-observed": 1})
            self.assertEqual(join_dates["#ALPHA"]["joined_at"], "2026-05-04T00:00:00+00:00")
            self.assertEqual(join_dates["#ALPHA"]["source"], "auto-baseline")
            self.assertEqual(join_dates["#BETA"]["joined_at"], "2026-06-29T00:00:00+00:00")
            self.assertEqual(join_dates["#BETA"]["source"], "auto-observed")
            self.assertEqual(store.get_setting(JOIN_DATE_BASELINE_SETTING), "1")

            inserted, source_counts = sync_roster_join_dates(
                store,
                FakeClashClient(
                    [
                        {"tag": "#ALPHA", "name": "alphawolf143"},
                        {"tag": "#BETA", "name": "Beta"},
                        {"tag": "#NEW", "name": "New Join"},
                    ]
                ),
                "#CLAN",
                second_now,
            )
            join_dates = store.get_member_join_date_map()

            self.assertEqual(inserted, 1)
            self.assertEqual(source_counts, {"auto-roster": 1})
            self.assertEqual(join_dates["#ALPHA"]["joined_at"], "2026-05-04T00:00:00+00:00")
            self.assertEqual(join_dates["#NEW"]["joined_at"], second_now.isoformat())


if __name__ == "__main__":
    unittest.main()
