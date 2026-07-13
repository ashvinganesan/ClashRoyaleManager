import datetime as dt
import tempfile
import unittest
from pathlib import Path


from microbot.storage import Store


class MicrobotStorageTests(unittest.TestCase):
    def test_verified_role_setting_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()

            self.assertIsNone(store.get_verified_role_id())

            store.set_verified_role_id(123456789)

            self.assertEqual(store.get_verified_role_id(), 123456789)

    def test_clan_status_role_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()

            self.assertIsNone(store.get_elder_role_id())
            self.assertIsNone(store.get_coleader_role_id())

            store.set_elder_role_id(111)
            store.set_coleader_role_id(222)

            self.assertEqual(store.get_elder_role_id(), 111)
            self.assertEqual(store.get_coleader_role_id(), 222)

    def test_verification_channel_setting_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()

            self.assertIsNone(store.get_verification_channel_id())

            store.set_verification_channel_id(987654321)

            self.assertEqual(store.get_verification_channel_id(), 987654321)

    def test_auto_verification_setting_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()

            self.assertFalse(store.get_auto_verification_enabled())

            store.set_auto_verification_enabled(True)
            self.assertTrue(store.get_auto_verification_enabled())

            store.set_auto_verification_enabled(False)
            self.assertFalse(store.get_auto_verification_enabled())

    def test_kick_threshold_setting_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()

            self.assertIsNone(store.get_kick_threshold())

            store.set_kick_threshold(2000)

            self.assertEqual(store.get_kick_threshold(), 2000)

    def test_promotion_threshold_setting_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()

            self.assertIsNone(store.get_promotion_threshold())

            store.set_promotion_threshold(2500)

            self.assertEqual(store.get_promotion_threshold(), 2500)

    def test_invalid_verified_role_setting_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()
            store.set_setting("verified_role_id", "not-a-number")

            self.assertIsNone(store.get_verified_role_id())

    def test_invalid_clan_status_role_settings_return_none(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()
            store.set_setting("elder_role_id", "not-a-number")
            store.set_setting("coleader_role_id", "not-a-number")

            self.assertIsNone(store.get_elder_role_id())
            self.assertIsNone(store.get_coleader_role_id())

    def test_remove_link_by_discord_id_removes_link(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()
            store.approve_challenge(
                challenge_id=99,
                reviewer_discord_id=1,
                discord_id=2,
                discord_name="Tester",
                player_tag="#ABC123",
                player_name="Player",
                clan_tag="#CLAN",
                clan_name="Clan",
            )

            removed = store.remove_link_by_discord_id(2)

            self.assertIsNotNone(removed)
            self.assertEqual(removed["player_tag"], "#ABC123")
            self.assertIsNone(store.get_link_by_discord_id(2))

    def test_get_pending_challenge_for_discord_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()

            store.create_challenge(
                discord_id=2,
                discord_name="Tester",
                player_tag="#ABC123",
                player_name="Player",
                challenge_code="CR-TEST12",
                ttl_minutes=30,
            )

            challenge = store.get_pending_challenge_for_discord_id(2)

            self.assertIsNotNone(challenge)
            self.assertEqual(challenge["player_tag"], "#ABC123")

    def test_direct_verification_links_account_and_approves_matching_challenge(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()

            store.create_challenge(
                discord_id=2,
                discord_name="Tester",
                player_tag="#ABC123",
                player_name="Player",
                challenge_code="CR-TEST12",
                ttl_minutes=-1,
            )

            store.approve_direct_verification(
                reviewer_discord_id=1,
                discord_id=2,
                discord_name="Tester",
                player_tag="#ABC123",
                player_name="Player",
                clan_tag="#CLAN",
                clan_name="Clan",
            )

            link = store.get_link_by_discord_id(2)

            with store.connect() as connection:
                challenge = connection.execute(
                    "SELECT status, reviewed_by_discord_id FROM verification_challenges WHERE discord_id = ?",
                    (2,),
                ).fetchone()

            self.assertIsNotNone(link)
            self.assertEqual(link["player_tag"], "#ABC123")
            self.assertEqual(challenge["status"], "approved")
            self.assertEqual(challenge["reviewed_by_discord_id"], 1)

    def test_member_presence_keeps_earliest_seen(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()
            newer = dt.datetime(2026, 7, 13, tzinfo=dt.timezone.utc)
            older = dt.datetime(2026, 6, 29, tzinfo=dt.timezone.utc)

            store.upsert_member_presence("#ABC123", "Player", "#CLAN", newer, "current roster")
            store.upsert_member_presence("#ABC123", "Player", "#CLAN", older, "river race log")

            presence = store.get_member_presence_map()["#ABC123"]

            self.assertEqual(presence["first_seen_at"], older.isoformat())
            self.assertEqual(presence["first_seen_source"], "river race log")
            self.assertEqual(presence["last_seen_at"], newer.isoformat())


if __name__ == "__main__":
    unittest.main()
