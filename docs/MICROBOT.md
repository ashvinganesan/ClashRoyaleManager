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
- `/confirm_verification <member> <player_tag>` lets a leader approve the link after seeing the code.
- `/me` shows the member's linked account.
- `/bot_health` confirms the bot is online.

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
