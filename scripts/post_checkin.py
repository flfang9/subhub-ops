#!/usr/bin/env python3
"""Post the Monday check-in to #building-in-public, and @-mention up to 5 App
Leaders who joined the server in the last week so the thread has someone to
answer first.

Who gets mentioned (all pure logic, see pick_new_leaders):
  - holds the App Leaders role (looked up by name at runtime), not a bot,
    not Adapty Team / Admin
  - joined the server 1 to 7 days ago: under 24h they have not had the intro DM
    yet, over 7 days and the previous check-in already had them
  - never mentioned in a previous check-in (the script reads its own last 100
    posts in the channel, so cron drift between weeks cannot double-tag anyone)
  - newest join first, max 5

The audit log is 403 for this bot, so "new" means joined_at (server join), not
when the role was granted.

The mention feature must never block the post: any failure reading roles,
members or history prints one line and the check-in goes out with no mentions.

    DRY_RUN=true DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/post_checkin.py
    TEST_DELETE=true ...   # posts then deletes; nobody is notified

Env: CHANNEL_ID, GUILD_ID, MENTION_LIMIT (5), MENTION_WINDOW_DAYS (7),
MENTION_MIN_AGE_HOURS (24), DRY_RUN, TEST_DELETE.
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # repo root, so any cwd works
API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/flfang9/subhub-ops, 1.0)"

CHANNEL_ID = os.environ.get("CHANNEL_ID", "1471517459617026162")  # building-in-public
GUILD_ID = os.environ.get("GUILD_ID", "878003622917587034")
BOT_USER_ID = os.environ.get("BOT_USER_ID", "1523747363087450203")  # the SubHub bot
ROLE_NAME = "App Leaders"
TEAM_ROLES = {"adapty team", "admin"}
CHECKIN_PREFIX = "**monday check-in**"
PLACEHOLDER = "{new_leaders}"

TOKEN = ""   # set in main(), so importing this module needs no secret


def req(method, path, body=None):
    """Discord REST call. Retries 429s, raises on anything else non-2xx."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json",
               "User-Agent": UA}
    for _ in range(8):
        r = urllib.request.Request(API + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(r) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    wait = float(json.load(e).get("retry_after", 2))
                except Exception:
                    wait = 2.0
                time.sleep(wait + 0.2)
                continue
            raise
    raise RuntimeError(f"rate-limited too long: {method} {path}")


# ---- pure logic (no I/O, unit tested in test_post_checkin.py) ----------------

def parse_joined_at(value):
    """Discord timestamp -> aware datetime, or None if missing / unparseable."""
    if not isinstance(value, str) or not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def pick_new_leaders(members, role_id, team_role_ids, now, already_mentioned,
                     limit=5, window_days=7, min_age_hours=24):
    """App Leaders who joined the server between min_age_hours and window_days
    ago and have never been mentioned before. Newest first, at most limit."""
    team = {str(r) for r in (team_role_ids or ())}
    seen = {str(u) for u in (already_mentioned or ())}
    oldest = now - timedelta(days=window_days)
    newest = now - timedelta(hours=min_age_hours)

    found = []
    for m in members or ():
        user = m.get("user") or {}
        uid = user.get("id")
        if not uid or str(uid) in seen or user.get("bot"):
            continue
        roles = {str(r) for r in (m.get("roles") or ())}
        if str(role_id) not in roles or roles & team:
            continue
        joined = parse_joined_at(m.get("joined_at"))
        if joined is None or joined < oldest or joined > newest:
            continue
        found.append((joined, m))

    found.sort(key=lambda pair: pair[0], reverse=True)
    return [m for _, m in found[:limit]]


def previous_mentions(messages, bot_user_id):
    """Every user id this bot has already @-mentioned in a check-in post."""
    out = set()
    for m in messages or ():
        author = m.get("author") or {}
        if str(author.get("id")) != str(bot_user_id):
            continue
        if not (m.get("content") or "").startswith(CHECKIN_PREFIX):
            continue
        for u in m.get("mentions") or ():
            if u.get("id"):
                out.add(str(u["id"]))
    return out


def compose(content_template, line_template, picks):
    """Fill the {new_leaders} line, or drop it entirely when nobody qualifies."""
    if picks:
        mentions = " ".join(f"<@{(m.get('user') or {}).get('id')}>" for m in picks)
        line = line_template.strip().format(mentions=mentions)
        out = content_template.replace(PLACEHOLDER, line)
    else:
        out = "\n".join(ln for ln in content_template.splitlines()
                        if ln.strip() != PLACEHOLDER)
    return out.strip()


# ---- I/O --------------------------------------------------------------------

def all_members():
    out, after = [], "0"
    while True:
        page = req("GET", f"/guilds/{GUILD_ID}/members?limit=1000&after={after}")
        if not page:
            break
        out.extend(page)
        if len(page) < 1000:
            break
        after = page[-1]["user"]["id"]
    return out


def gather_picks(now, limit, window_days, min_age_hours):
    """Read roles + members + our own history. Raises; the caller falls back."""
    roles = req("GET", f"/guilds/{GUILD_ID}/roles")
    if not isinstance(roles, list):
        raise RuntimeError(f"roles endpoint returned {type(roles).__name__}")
    role = next((r for r in roles if (r.get("name") or "").lower() == ROLE_NAME.lower()), None)
    if not role:
        raise RuntimeError(f"role {ROLE_NAME!r} not found in guild {GUILD_ID}")
    team_ids = [r["id"] for r in roles if (r.get("name") or "").lower() in TEAM_ROLES]

    members = all_members()
    if not members:
        raise RuntimeError("member list came back empty")

    history = req("GET", f"/channels/{CHANNEL_ID}/messages?limit=100")
    if not isinstance(history, list):
        raise RuntimeError(f"messages endpoint returned {type(history).__name__}")
    already = previous_mentions(history, BOT_USER_ID)

    leaders = sum(1 for m in members if role["id"] in (m.get("roles") or []))
    print(f"  {len(members)} members, {leaders} hold {ROLE_NAME}, "
          f"{len(already)} mentioned in past check-ins")
    return pick_new_leaders(members, role["id"], team_ids, now, already,
                            limit, window_days, min_age_hours)


def main():
    global TOKEN
    TOKEN = os.environ["DISCORD_BOT_TOKEN"].strip()
    dry_run = os.environ.get("DRY_RUN") == "true"
    test_delete = os.environ.get("TEST_DELETE") == "true"
    limit = int(os.environ.get("MENTION_LIMIT", "5"))
    window_days = int(os.environ.get("MENTION_WINDOW_DAYS", "7"))
    min_age_hours = int(os.environ.get("MENTION_MIN_AGE_HOURS", "24"))

    content_template = (ROOT / "checkin-message.md").read_text()
    line_template = (ROOT / "checkin-new-leaders.md").read_text()

    print(f"new app leaders, joined {min_age_hours}h to {window_days}d ago, max {limit}:")
    try:
        picks = gather_picks(datetime.now(timezone.utc), limit, window_days, min_age_hours)
    except Exception as e:
        print(f"  mentions OFF ({type(e).__name__}: {e}); posting without them")
        picks = []
    for m in picks:
        u = m.get("user") or {}
        print(f"  + {u.get('username')} ({u.get('id')}) joined {m.get('joined_at')}")
    if not picks:
        print("  (nobody qualifies this week)")

    content = compose(content_template, line_template, picks)
    ids = [str((m.get("user") or {}).get("id")) for m in picks]
    # parse: [] means role and @everyone pings are impossible, whatever the copy says.
    # test mode renders the <@id> text but notifies nobody.
    allowed = {"parse": [], "users": [] if test_delete else ids}

    if dry_run:
        print(f"\nallowed_mentions: {json.dumps(allowed)}")
        print("--- message (DRY RUN, nothing posted) ---")
        print(content)
        print("--- end ---")
        return

    msg = req("POST", f"/channels/{CHANNEL_ID}/messages",
              {"content": content, "allowed_mentions": allowed})
    print("posted message", msg["id"])

    if test_delete:
        time.sleep(2)
        req("DELETE", f"/channels/{CHANNEL_ID}/messages/{msg['id']}")
        print("test mode: deleted", msg["id"])


if __name__ == "__main__":
    main()
