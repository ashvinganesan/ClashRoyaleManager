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
- `/confirm_verification <member> [player_tag]` lets a Discord admin approve the link after seeing the code.
- `/remove_verification <member>` lets a Discord admin remove a member's linked account and verified role.
- `/set_verified_role <role>` sets the role assigned after successful verification.
- `/set_verification_channel <channel>` sets the leader-only channel where pending verification requests are posted.
- `/verification_config` shows the current verification role and review channel settings.
- `/set_kick_threshold <min_fame>` sets the war fame threshold used for kick suggestions.
- `/set_promotion_threshold <min_average_fame>` sets the average war fame threshold used for promotion suggestions.
- `/war_config` shows the current war stat settings.
- `/war_stats` posts public current Clan War stats, rolling completed-war averages, first-seen dates, suggested promotions, and suggested kick/demotion candidates.
- `/show_stats [player] [member]` posts public war stats for one player by IGN, player tag, verified Discord member, or your own verified account.
- `/me` shows the member's linked account.
- `/bot_health` confirms the bot is online.

## Discord Verification Setup

1. Create a `Verified` role in Discord.
2. Move the bot's role above `Verified` in Server Settings > Roles.
3. Make sure the bot has `Manage Roles` and `Manage Nicknames`.
4. Run `/set_verified_role @Verified`.
5. Create a leader-only `#verification-confirmation` channel, or run `/set_verification_channel #channel-name` for a different channel.
6. Leave one member verification channel visible to `@everyone`.
7. Hide the rest of the server from `@everyone`, then allow `Verified` to view and send messages in the normal categories/channels.

Only users with Discord administrator permission can run `/confirm_verification`, `/remove_verification`, `/set_verified_role`, `/set_verification_channel`, `/set_kick_threshold`, `/set_promotion_threshold`, `/war_config`, and `/verification_config`.

The official Clash Royale API does not expose clan chat messages, so the microbot cannot safely auto-read clan chat. The supported flow is: a member posts the generated code in Clash Royale, the bot posts a pending request in the leader review channel, and an admin confirms after seeing the code in-game. Confirmation assigns the verified role and tries to set the member's server nickname to their Clash Royale IGN. Discord does not allow bots to change the server owner's nickname.

## War Stats

`/war_stats` combines the current river race with recent completed races from the Clash Royale API. It also records when the bot first sees each member in the current roster or river race history.

`/show_stats player:DaddyRizz` shows the same current-war, rolling-average, first-seen, promotion, and kick/demotion logic for one member. You can also use a player tag, `/show_stats member:@someone` for a verified Discord member, or `/show_stats` for your own verified account.

The default kick suggestion threshold is `2000` war fame. The default promotion suggestion threshold is `2500` average war fame.

Leaders can change them with:

```text
/set_kick_threshold 2000
/set_promotion_threshold 2500
```

Leaderboard eligibility requires at least 2 completed wars and 14 days first-seen tenure. Promotion suggestions require at least 3 completed wars, 14 days first-seen tenure, and an in-game role below co-leader. War rows include colored role markers for member, elder, co-leader, and leader.

Suggested kick/demotion candidates must be below the current-war threshold and also have either no completed-war average yet or a rolling average below the kick threshold. Members above the current-war threshold or at/above the rolling-average threshold stay off the suggested kick/demotion list. First-seen is shown as context for leaders, not as an automatic excuse.

Clash Royale does not expose true clan join dates. The bot shows "first seen" dates based on bot/API observations, so that data becomes more accurate as the bot keeps running.

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
