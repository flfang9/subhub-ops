# subhub-ops

Automation for the SubHub Discord community (Subscriptions Hub by Adapty).

| Workflow | Schedule | Status |
|---|---|---|
| `monday-checkin` | Mondays 11:00 UTC (7am EDT target) | **live** — posts `checkin-message.md` to #building-in-public as the SubHub bot. Cron is set 2h early on purpose: GitHub's schedule queue fired 2–3h late on Jul 27 + Aug 3, so 11:00 UTC lands ~9am ET in practice. If it ever posts too early, bump back toward 12:00 |
| `intro-dm` | daily 15:00 UTC | **live** (`INTRO_DM_ENABLED=true`). DMs `intro-dm.md` to members who joined 24–48h ago (`{name}` = their display name). Copy v2 since 2026-08-03: asks for a reply to the DM instead of a public post — replies land in the **bot's** inbox, read them with `DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/check_dm_replies.py` |
| `app-leaders` (verifier) | :15 and :45 every hour | **built, disabled**. Watches `mrr-verification-*` tickets, acts on staff ✅/❌, grants the App Leaders role, posts `welcome-app-leader.md` / `reject-app-leader.md`. Flips on when `APP_LEADERS_ENABLED=true` **and** the bot has perms (below) |
| `app-leaders` (nudge) | Mondays 14:00 UTC | **built, disabled**. Same workflow with `NUDGE=1`: DMs `nudge-app-leaders.md` to members holding App Leaders (Pending) who never opened a ticket. Max 2 nudges per person, ever |

Edit the message copy by editing the `.md` files — next run picks it up. Secrets: `DISCORD_BOT_TOKEN` (the SubHub audit bot). Test the Monday post end-to-end via Actions → monday-checkin → Run workflow with `test_mode` (posts + deletes in ~2s).

## App Leaders pipeline

Replaces the old Five/Six Figures Club roles + categories with one gated room: **App Leaders** ($10k+ MRR, verified).

**One-time migration** (`scripts/app_leaders_migrate.py`, run locally, not in CI):

```bash
cd ~/Coding/subhub-ops
DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/app_leaders_migrate.py            # dry run
DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/app_leaders_migrate.py --execute  # apply
```

Dry run prints every write it would make and the config it would generate; nothing is touched. `--execute` runs in order: create the App Leaders role → grant it to already-verified holders → rename the Pending role → channel renames/moves/overwrites + delete the Six Figures category → post `join-app-leaders.md` in #join-app-leaders → delete the four old MRR roles last. It writes `scripts/app_leaders_config.json`, which the verifier reads (the verifier no-ops until that file exists).

**Freddy-side Discord UI checklist** (must be done before flipping the switch):

1. Bot perms for **App Leaders** (`1523747363087450203`): Manage Roles, Manage Channels, Send Messages, View Channels, Read Message History, Add Reactions.
2. Give the bot's **SubHub Audit** role access to the **MRR Verification** category, then *Sync Permissions* on the existing ticket channels — otherwise the verifier 403s per ticket (it skips + counts, doesn't crash).
3. Server Settings → Roles: drag **SubHub Audit** above the whole MRR role block (all five old MRR roles *and* the new App Leaders role) — a bot can't touch roles that sit above its own, and the migration renames/deletes those. Do this BEFORE running the migration.
4. Server Settings → Onboarding: replace the old Five/Six Figures answers with one "My app makes $10k+ MRR" option → assigns App Leaders (Pending) + reveals #join-app-leaders.
5. Delete Freddy's old June 8 messages in #join-app-leaders (they still pitch Five/Six Figures; the bot can't delete another user's messages), and update the Dyno ticket-panel embed copy to match.
6. Set repo variable `APP_LEADERS_ENABLED=true` (Settings → Secrets and variables → Actions → Variables).

**Kill switch:** set `APP_LEADERS_ENABLED` to anything but `true` (or delete it) — the job's `if:` gate stops both the sweeps and the Monday nudge immediately. Copy edits are just the `.md` files. Every write is latched behind the `[AL-VERIFY]` embed footer, so re-running is always safe.
