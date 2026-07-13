# Micro Bot

`microbot` is a tiny SQLite-backed Discord bot intended for the Oracle `VM.Standard.E2.1.Micro` instance.

It is intentionally separate from the full historical manager while deployment is constrained:

- No Docker.
- No MySQL.
- No OpenCV/Tesseract.
- No NumPy.
- SQLite for account links and verification challenges.
- `discord.py` plus Python standard library.

## Commands

- `/verify <player_tag>` creates a short code for the member to post in Clash Royale clan chat.
- `/confirm_verification <member> <player_tag>` lets a Discord admin approve the link after seeing the code.
- `/remove_verification <member>` lets a Discord admin remove a member's linked account and verified role.
- `/set_verified_role <role>` sets the role assigned after successful verification.
- `/set_verification_channel <channel>` sets the leader-only channel where pending verification requests are posted.
- `/verification_config` shows the current verification role and review channel settings.
- `/war_stats` posts the current Clan War/River Race snapshot for the configured clan.
- `/me` shows the member's linked account.
- `/bot_health` confirms the bot is online.

## Discord Verification Setup

1. Create a `Verified` role in Discord.
2. Move the bot's role above `Verified` in Server Settings > Roles.
3. Make sure the bot has `Manage Roles`.
4. Run `/set_verified_role @Verified`.
5. Create a leader-only verification review channel and run `/set_verification_channel #channel-name`.
6. Leave one member verification channel visible to `@everyone`.
7. Hide the rest of the server from `@everyone`, then allow `Verified` to view and send messages in the normal categories/channels.

Only users with Discord administrator permission can run `/confirm_verification`, `/remove_verification`, `/set_verified_role`, `/set_verification_channel`, and `/verification_config`.

The official Clash Royale API does not expose clan chat messages, so the microbot cannot safely auto-read clan chat. The supported flow is: a member posts the generated code in Clash Royale, the bot posts a pending request in the leader review channel, and an admin confirms after seeing the code in-game.

## Run

```bash
python3 -m microbot.bot
```

## systemd

The production service unit lives at:

```text
deploy/systemd/clash-royale-microbot.service
```

Install it on the VM:

```bash
sudo cp deploy/systemd/clash-royale-microbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable clash-royale-microbot
sudo systemctl start clash-royale-microbot
```

Check logs:

```bash
journalctl -u clash-royale-microbot -f
```

Required environment variables:

```dotenv
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
CLASH_ROYALE_API_TOKEN=
CLAN_TAG=
MICROBOT_DATABASE_PATH=data/microbot.sqlite3
```

Optional:

```dotenv
DISCORD_VERIFIED_ROLE_ID=
VERIFICATION_TTL_MINUTES=30
```
