# subhub-ops

Automation for the SubHub Discord community (Subscriptions Hub by Adapty).

| Workflow | Schedule | Status |
|---|---|---|
| `monday-checkin` | Mondays 13:00 UTC (9am EDT; 8am in winter) | **live** — posts `checkin-message.md` to #building-in-public as the SubHub bot |
| `intro-dm` | daily 15:00 UTC | **parked** — enable by setting repo variable `INTRO_DM_ENABLED=true`. DMs `intro-dm.md` to members who joined 24–48h ago (`{name}` = their display name) |

Edit the message copy by editing the `.md` files — next run picks it up. Secrets: `DISCORD_BOT_TOKEN` (the SubHub audit bot). Test the Monday post end-to-end via Actions → monday-checkin → Run workflow with `test_mode` (posts + deletes in ~2s).
