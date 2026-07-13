import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ClashRoyaleManager"))

from config import settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.original_environ = os.environ.copy()
        settings._DOTENV_LOADED = False

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_environ)
        settings._DOTENV_LOADED = False

    def test_required_env_reports_missing_name(self):
        with self.assertRaisesRegex(settings.ConfigurationError, "MISSING_SETTING"):
            settings.get_env("MISSING_SETTING")

    def test_dotenv_loads_without_overriding_environment(self):
        os.environ["MYSQL_HOST"] = "from-environment"

        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join([
                    "MYSQL_HOST=from-file",
                    "MYSQL_USER='bot_user'",
                    'MYSQL_DATABASE="clash_royale_manager"',
                ]),
                encoding="utf-8",
            )

            settings.load_dotenv(env_path)

        self.assertEqual(os.environ["MYSQL_HOST"], "from-environment")
        self.assertEqual(os.environ["MYSQL_USER"], "bot_user")
        self.assertEqual(os.environ["MYSQL_DATABASE"], "clash_royale_manager")

    def test_database_config_reads_expected_variables(self):
        os.environ.update(
            {
                "MYSQL_HOST": "localhost",
                "MYSQL_PORT": "3307",
                "MYSQL_USER": "bot_user",
                "MYSQL_PASSWORD": "secret",
                "MYSQL_DATABASE": "clash_royale_manager",
            }
        )

        config = settings.get_database_config()

        self.assertEqual(config.host, "localhost")
        self.assertEqual(config.port, 3307)
        self.assertEqual(config.user, "bot_user")
        self.assertEqual(config.password, "secret")
        self.assertEqual(config.database, "clash_royale_manager")


if __name__ == "__main__":
    unittest.main()
