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

    def test_verification_channel_setting_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()

            self.assertIsNone(store.get_verification_channel_id())

            store.set_verification_channel_id(987654321)

            self.assertEqual(store.get_verification_channel_id(), 987654321)

    def test_invalid_verified_role_setting_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()
            store.set_setting("verified_role_id", "not-a-number")

            self.assertIsNone(store.get_verified_role_id())

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


if __name__ == "__main__":
    unittest.main()
