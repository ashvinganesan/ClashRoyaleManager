import importlib.util
import unittest


DISCORD_AVAILABLE = importlib.util.find_spec("discord") is not None

if DISCORD_AVAILABLE:
    from microbot.bot import can_confirm_verification_user


class FakePermissions:
    def __init__(self, administrator=False):
        self.administrator = administrator


class FakeRole:
    def __init__(self, name):
        self.name = name


class FakeMember:
    def __init__(self, role_names=None, administrator=False):
        self.guild_permissions = FakePermissions(administrator=administrator)
        self.roles = [FakeRole(name) for name in (role_names or [])]


@unittest.skipUnless(DISCORD_AVAILABLE, "discord.py is not installed")
class MicrobotPermissionTests(unittest.TestCase):
    def test_admin_can_confirm_verification(self):
        self.assertTrue(can_confirm_verification_user(FakeMember(administrator=True)))

    def test_elder_role_can_confirm_verification(self):
        self.assertTrue(can_confirm_verification_user(FakeMember(role_names=["Elder"])))

    def test_non_admin_without_elder_role_cannot_confirm_verification(self):
        self.assertFalse(can_confirm_verification_user(FakeMember(role_names=["Verified"])))


if __name__ == "__main__":
    unittest.main()
