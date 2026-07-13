# Owner Actions

This project can proceed with placeholders, but these actions will eventually require the clan owner.

## Now

- Confirm the fork URL is `https://github.com/ashvinganesan/ClashRoyaleManager`.
- Keep real tokens/passwords out of Git.

## Before Bot Testing In Discord

- Create a Discord application and bot.
- Enable Server Members Intent.
- Enable Message Content Intent if we keep message-based screenshot parsing.
- Invite the bot to a test Discord server first.
- Create or identify test channels for admin alerts, exports, war reminders, new member info, and strike review.
- Create or identify leadership/admin roles.

## Before Clash Royale API Testing

- Create a Clash Royale developer account.
- Create an API key for the public IP of the machine running the bot.
- Provide the clan tag in `.env`, not in source code.

## Before Production Hosting

- Create or sign in to Oracle Cloud Infrastructure.
- Provision an Always Free eligible VM if capacity is available.
- Reserve a public IP.
- Configure SSH keys.
- Keep MySQL private to Docker or localhost.
- Create a backup destination outside the VM.

## Secrets Rule

Do not paste tokens, passwords, API keys, SSH private keys, or production `.env` contents into Git, Discord, screenshots, or issue text.
