"""Tiny Discord bot entry point."""

import logging
import secrets
import string
from typing import Any, Optional

import discord
from discord import app_commands

from microbot.clash_api import ClashApiError, ClashClient, ClashNotFound
from microbot.config import Settings, load_settings, normalize_tag
from microbot.storage import Store


LOG = logging.getLogger("microbot")


def discord_name(user: Any) -> str:
    """Return a stable display name for logs/storage."""
    discriminator = getattr(user, "discriminator", "0")
    return user.name if discriminator == "0" else f"{user.name}#{discriminator}"


def make_code() -> str:
    """Create a short verification code."""
    alphabet = string.ascii_uppercase + string.digits
    return "CR-" + "".join(secrets.choice(alphabet) for _ in range(6))


def player_clan(player: dict) -> tuple[Optional[str], Optional[str]]:
    """Extract clan tag/name from a player payload."""
    clan = player.get("clan") or {}
    return clan.get("tag"), clan.get("name")


class MicroBot(discord.Client):
    """Minimal Discord client with slash commands."""

    def __init__(self, settings: Settings, store: Store, clash: ClashClient):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.settings = settings
        self.store = store
        self.clash = clash
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        """Register slash commands."""
        guild = discord.Object(id=self.settings.discord_guild_id) if self.settings.discord_guild_id else None

        if guild:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        """Log startup."""
        LOG.info("Micro bot ready as %s", self.user)


def build_bot() -> MicroBot:
    """Build the bot and commands."""
    settings = load_settings()
    store = Store(settings.database_path)
    store.initialize()
    clash = ClashClient(settings.clash_api_token)
    bot = MicroBot(settings, store, clash)

    @bot.tree.command(name="bot_health", description="Show whether the lightweight bot is online.")
    async def bot_health(interaction: discord.Interaction):
        await interaction.response.send_message("Online. SQLite store is initialized.", ephemeral=True)

    @bot.tree.command(name="me", description="Show your linked Clash Royale account.")
    async def me(interaction: discord.Interaction):
        link = store.get_link_by_discord_id(interaction.user.id)

        if link is None:
            await interaction.response.send_message("You are not verified yet. Run `/verify <player_tag>`.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"You are linked to {link['player_name']} `{link['player_tag']}`.",
            ephemeral=True,
        )

    @bot.tree.command(name="verify", description="Get a code to post in Clash Royale clan chat.")
    @app_commands.describe(player_tag="Your Clash Royale player tag")
    async def verify(interaction: discord.Interaction, player_tag: str):
        normalized_tag = normalize_tag(player_tag)

        if not normalized_tag:
            await interaction.response.send_message("Enter a valid Clash Royale player tag.", ephemeral=True)
            return

        if store.get_link_by_discord_id(interaction.user.id):
            await interaction.response.send_message("You are already verified.", ephemeral=True)
            return

        if store.get_link_by_player_tag(normalized_tag):
            await interaction.response.send_message("That player tag is already linked.", ephemeral=True)
            return

        try:
            player = clash.get_player(normalized_tag)
        except ClashNotFound:
            await interaction.response.send_message("That player tag does not exist.", ephemeral=True)
            return
        except ClashApiError:
            await interaction.response.send_message("The Clash Royale API is unavailable. Try again later.", ephemeral=True)
            return

        clan_tag, clan_name = player_clan(player)

        if settings.clan_tag and clan_tag != settings.clan_tag:
            await interaction.response.send_message("That player is not currently in the configured clan.", ephemeral=True)
            return

        code = make_code()
        expires_at = store.create_challenge(
            interaction.user.id,
            discord_name(interaction.user),
            player["tag"],
            player["name"],
            code,
            settings.verification_ttl_minutes,
        )
        message = (
            f"Post this exact code in Clash Royale clan chat: `{code}`\n"
            "Then ask a leader to run `/confirm_verification` after they see it.\n"
            f"Player: {player['name']} `{player['tag']}`"
        )

        if clan_name:
            message += f"\nClan: {clan_name} `{clan_tag}`"

        message += f"\nExpires: `{expires_at}`"
        await interaction.response.send_message(message, ephemeral=True)

    @bot.tree.command(name="confirm_verification", description="Leader confirmation after seeing a code in clan chat.")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.describe(member="Discord member who posted the code")
    @app_commands.describe(player_tag="Player tag being verified")
    async def confirm_verification(interaction: discord.Interaction, member: discord.Member, player_tag: str):
        normalized_tag = normalize_tag(player_tag)
        challenge = store.get_pending_challenge(member.id, normalized_tag)

        if challenge is None:
            await interaction.response.send_message("No active verification challenge found.", ephemeral=True)
            return

        try:
            player = clash.get_player(normalized_tag)
        except ClashApiError:
            await interaction.response.send_message("The Clash Royale API is unavailable. Try again later.", ephemeral=True)
            return

        clan_tag, clan_name = player_clan(player)
        store.approve_challenge(
            challenge["id"],
            interaction.user.id,
            member.id,
            discord_name(member),
            player["tag"],
            player["name"],
            clan_tag,
            clan_name,
        )

        if settings.verified_role_id:
            role = interaction.guild.get_role(settings.verified_role_id) if interaction.guild else None

            if role:
                await member.add_roles(role)

        await interaction.response.send_message(
            f"Verified {member.mention} as {player['name']} `{player['tag']}`.",
            ephemeral=True,
        )

    @confirm_verification.error
    async def confirm_verification_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You do not have permission to confirm verifications.", ephemeral=True)
        else:
            LOG.exception("Unexpected command error", exc_info=error)
            await interaction.response.send_message("Unexpected error.", ephemeral=True)

    return bot


def main():
    """Run the micro bot."""
    logging.basicConfig(level=logging.INFO)
    bot = build_bot()
    bot.run(bot.settings.discord_token)


if __name__ == "__main__":
    main()
