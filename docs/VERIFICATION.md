# Discord Verification

The official Clash Royale API can verify player profiles and clan membership, but it does not expose clan chat messages. That means the bot cannot automatically read clan chat to prove ownership of an account.

The first safe verification workflow is human-assisted:

1. A Discord member runs `/verify <player_tag>`.
2. The bot checks that the player tag exists and is currently in a tracked clan.
3. The bot creates a short verification code such as `CR-A1B2C3`.
4. The member posts that exact code in Clash Royale clan chat.
5. A leader with Discord administrator permission or the `Elder` role who can see clan chat runs `/confirm_verification <member> <player_tag>`.
6. The bot links the Discord account to the Clash Royale player, updates roles/nickname, and posts the new-member info embed.

If the active challenge expires before a leader handles it, the leader can still run the fallback command from the leader-channel message:

```text
/confirm_verification member:@member player_tag:#PLAYER_TAG
```

That path direct-verifies the member by admin action after confirming the player tag still belongs to the configured clan.

Admins can enable a lower-friction mode with:

```text
/set_auto_verification enabled:true
```

When enabled, `/verify player_tag:#PLAYER_TAG` immediately auto-confirms the member if the tag is currently in the configured clan. The bot posts an "Auto Confirmed Clash Royale Verification" audit message in the leader verification channel. Disable it with `/set_auto_verification enabled:false` to return to clan-chat code confirmation.

## Why Manual Confirmation Is Required

Reading Clash Royale clan chat would require unsupported automation or scraping. This project should stay on official APIs and avoid account-risky behavior.

## Future Options

- Add a Discord button workflow for leaders to approve pending challenges.
- Add a `/pending_verifications` leadership command.
- Expire old pending challenges from a scheduled cleanup job.
- Add a fuller audit log for admin direct-verification decisions.
