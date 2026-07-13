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

    def test_invalid_verified_role_setting_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "microbot.sqlite3"))
            store.initialize()
            store.set_setting("verified_role_id", "not-a-number")

            self.assertIsNone(store.get_verified_role_id())


if __name__ == "__main__":
    unittest.main()
