# subhub-ops

Automation for the SubHub Discord community (Subscriptions Hub by Adapty).

| Workflow | Schedule | Status |
|---|---|---|
| `monday-checkin` | Mondays 11:00 UTC (7am EDT target) | **live** — posts `checkin-message.md` to #building-in-public as the SubHub bot. Cron is set 2h early on purpose: GitHub's schedule queue fired 2–3h late on Jul 27 + Aug 3, so 11:00 UTC lands ~9am ET in practice. If it ever posts too early, bump back toward 12:00 |
| `intro-dm` | daily 15:00 UTC | **live** (`INTRO_DM_ENABLED=true`). DMs `intro-dm.md` to members who joined 24–48h ago (`{name}` = their display name). Copy v2 since 2026-08-03: asks for a reply to the DM instead of a public post — replies land in the **bot's** inbox, read them with `DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/check_dm_replies.py` |

Edit the message copy by editing the `.md` files — next run picks it up. Secrets: `DISCORD_BOT_TOKEN` (the SubHub audit bot). Test the Monday post end-to-end via Actions → monday-checkin → Run workflow with `test_mode` (posts + deletes in ~2s).
