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
- `/confirm_verification <member> [player_tag]` lets a Discord admin or member with the `Elder` role approve the link after seeing the code. If the active challenge expired, including `player_tag` direct-verifies the member after checking the player is still in the clan.
- `/remove_verification <member>` lets a Discord admin remove a member's linked account and verified role.
- `/set_verified_role <role>` sets the role assigned after successful verification.
- `/set_elder_role <role>` sets the Discord role assigned when a verified player is an in-game Elder.
- `/set_coleader_role <role>` sets the Discord role assigned when a verified player is an in-game Co-Leader or Leader.
- `/set_verification_channel <channel>` sets the leader-only channel where pending verification requests are posted.
- `/set_auto_verification <enabled>` toggles auto-confirming `/verify` when the player tag is currently in the clan.
- `/verification_config` shows the current verification roles, review channel, and auto-verification settings.
- `/set_kick_threshold <min_fame>` sets the war fame threshold used for kick suggestions.
- `/set_promotion_threshold <min_average_fame>` sets the average war fame threshold used for promotion suggestions.
- `/war_config` shows the current war stat settings.
- `/war_stats` posts public current Clan War stats, rolling completed-war averages, first-seen dates, suggested promotions, and suggested kick/demotion candidates.
- `/last_war_bottom` posts a public rank 41+ audit from the latest completed war.
- `/show_stats [player] [member]` and `/show [player] [member]` post public war stats for one player by IGN, player tag, verified Discord member, or your own verified account. They state whether the player is still in the current clan roster.
- `/me` shows the member's linked account.
- `/bot_health` confirms the bot is online.

## Discord Verification Setup

1. Create `Verified`, `Elder`, and `Co-Leader` roles in Discord.
2. Move the bot's role above those roles in Server Settings > Roles.
3. Make sure the bot has `Manage Roles` and `Manage Nicknames`.
4. Run `/set_verified_role @Verified`.
5. Optional: run `/set_elder_role @Elder` and `/set_coleader_role @Co-Leader`. If you skip this, the bot auto-detects roles named `Elder` and `Co-Leader`.
6. Create a leader-only `#verification-confirmation` channel, or run `/set_verification_channel #channel-name` for a different channel.
7. Leave one member verification channel visible to `@everyone`.
8. Hide the rest of the server from `@everyone`, then allow `Verified` to view channels, send messages, and use application commands in the normal categories/channels.

Users with Discord administrator permission or the `Elder` role can run `/confirm_verification`. Only users with Discord administrator permission can run `/remove_verification`, `/set_verified_role`, `/set_elder_role`, `/set_coleader_role`, `/set_verification_channel`, `/set_auto_verification`, `/set_kick_threshold`, `/set_promotion_threshold`, `/war_config`, and `/verification_config`.

`/war_stats`, `/last_war_bottom`, `/show_stats`, and `/show` are public bot commands. If a verified member cannot see them in Discord's slash-command picker, check that their channel/category permissions include **Use Application Commands** for the `Verified` role and that the bot is allowed in that channel.

The official Clash Royale API does not expose clan chat messages, so the microbot cannot safely auto-read clan chat. The default flow is: a member posts the generated code in Clash Royale, the bot posts a pending request in the leader review channel, and an admin or Elder confirms after seeing the code in-game. If the request expires before a leader handles it, the fallback command with `player_tag` in the leader message can still direct-verify that member. Confirmation assigns the verified role, assigns `Elder` or `Co-Leader` when the player's current in-game role matches, and tries to set the member's server nickname to their Clash Royale IGN. Discord does not allow bots to change the server owner's nickname.

Auto verification is disabled by default. If an admin runs `/set_auto_verification enabled:true`, `/verify player_tag:#TAG` immediately auto-confirms the member when that tag is currently in the configured clan. The bot still posts an "Auto Confirmed Clash Royale Verification" audit message in the leader verification channel.

## War Stats

`/war_stats` combines the current river race with recent completed races from the Clash Royale API. It also records when the bot first sees each member in the current roster or river race history. During training days, the active score switches to the last completed war so the post-war reset does not make everyone look like they scored 0.

`/last_war_bottom` lists everyone who ranked below 40th in the latest completed war. It includes last-war fame, rolling full-war average, first-seen age, and whether the player is still in the clan or is already gone.

`/show player:DaddyRizz` or `/show_stats player:DaddyRizz` shows the same current-war, rolling-average, first-seen, promotion, and kick/demotion logic for one member. You can also use a player tag, `member:@someone` for a verified Discord member, or run `/show` for your own verified account.

The default kick suggestion threshold is `2000` war fame. The default promotion suggestion threshold is `2500` average war fame.

Leaders can change them with:

```text
/set_kick_threshold 2000
/set_promotion_threshold 2500
```

Leaderboard eligibility requires at least 2 full completed wars and 14 days first-seen tenure. Promotion suggestions require at least 3 full completed wars, 14 days first-seen tenure, and an in-game role below co-leader. War rows include colored role markers for member, elder, co-leader, and leader.

Suggested kick/demotion candidates must be below the active score threshold and also have either no full completed-war average yet or a rolling average below the kick threshold. The active score is current-war fame during battle periods and last-war fame during training periods. Members above the active score threshold or at/above the rolling-average threshold stay off the suggested kick/demotion list. Short samples are handled conservatively: if a member has fewer than 3 full wars and at least one full war at or above the kick threshold, the bot does not auto-suggest kick/demotion yet.

Clash Royale does not expose true clan join dates. The bot shows "first seen" dates based on bot/API observations, so that data becomes more accurate as the bot keeps running. Rolling averages only count wars where the member was first seen by the approximate start of battle day 1, based on the completed-war timestamp from the Clash Royale API; partial wars are shown but marked as not counted. If the bot first discovers a member from a completed river-race log, that first observed race can count when the score is high enough to show real participation.

## Run

```bash
python3 -m microbot.bot
```

## systemd

The production service unit lives at:

```text
deploy/systemd/clash-royale-microbot.service
```

The bot writes a heartbeat file while connected to Discord. The watchdog timer restarts only the bot service when that heartbeat is stale for 3 minutes, then reboots the VM if the heartbeat remains stale for 15 minutes.

Install the service and watchdog on the VM:

```bash
sudo cp deploy/systemd/clash-royale-microbot.service /etc/systemd/system/
sudo cp deploy/systemd/clash-royale-microbot-watchdog.service /etc/systemd/system/
sudo cp deploy/systemd/clash-royale-microbot-watchdog.timer /etc/systemd/system/
sudo cp deploy/bin/clash-royale-microbot-watchdog /usr/local/bin/
sudo chmod 755 /usr/local/bin/clash-royale-microbot-watchdog
sudo systemctl daemon-reload
sudo systemctl enable clash-royale-microbot
sudo systemctl enable clash-royale-microbot-watchdog.timer
sudo systemctl start clash-royale-microbot
sudo systemctl start clash-royale-microbot-watchdog.timer
```

Check logs:

```bash
journalctl -u clash-royale-microbot -f
```

## Micro VM Hardening

The Oracle `VM.Standard.E2.1.Micro` image has very little RAM. Keep SSH closed to internet-wide scanners and disable optional background collectors:

```bash
sudo SSH_ALLOWED_CIDR=x.x.x.x/32 /home/opc/ClashRoyaleManager/deploy/bin/harden-micro-vm
```

Use the current trusted public IP for `SSH_ALLOWED_CIDR`. If SSH stops working after an IP change, update the VM firewall from an Oracle console session or temporarily adjust the VCN security rules, then rerun this command with the new CIDR.

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
VERIFICATION_TTL_MINUTES=2880
MICROBOT_HEARTBEAT_PATH=/run/clash-royale-microbot/heartbeat
```
