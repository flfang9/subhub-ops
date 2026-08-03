"""Print replies members sent to the intro DM.

The bot owns those DM channels, so replies land in its inbox, not Freddy's.
Run locally: DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/check_dm_replies.py
Opening a DM channel is idempotent, so we just re-open one per member who
joined since the intro-dm launch and read it back.
"""
import json, os, time, urllib.request, urllib.error
from datetime import datetime, timezone

TOKEN = os.environ["DISCORD_BOT_TOKEN"].strip()
GUILD_ID = os.environ.get("GUILD_ID", "878003622917587034")
API = "https://discord.com/api/v10"
LAUNCH = datetime(2026, 7, 25, tzinfo=timezone.utc)  # first DM window opened here

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    for _ in range(8):
        r = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": f"Bot {TOKEN}", "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://github.com/flfang9/subhub-ops, 1.0)"})
        try:
            with urllib.request.urlopen(r) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(json.load(e).get("retry_after", 2)) + 0.2)
                continue
            if e.code in (403, 404):
                return None
            raise
    raise RuntimeError(f"rate-limited too long: {path}")

members, after = [], "0"
while True:
    batch = req("GET", f"/guilds/{GUILD_ID}/members?limit=1000&after={after}")
    if not batch: break
    members += batch
    after = batch[-1]["user"]["id"]
    if len(batch) < 1000: break

targets = [m for m in members if not m["user"].get("bot")
           and datetime.fromisoformat(m["joined_at"].replace("Z", "+00:00")) >= LAUNCH]
print(f"checking {len(targets)} members joined since {LAUNCH.date()}")

replies = 0
for m in targets:
    dm = req("POST", "/users/@me/channels", {"recipient_id": m["user"]["id"]})
    if not dm: continue
    msgs = req("GET", f"/channels/{dm['id']}/messages?limit=50") or []
    theirs = [x for x in msgs if x["author"]["id"] == m["user"]["id"]]
    if theirs:
        replies += 1
        name = m["user"].get("global_name") or m["user"]["username"]
        print(f"\n=== {name} (@{m['user']['username']}) ===")
        for x in sorted(theirs, key=lambda x: x["timestamp"]):
            print(f"  [{x['timestamp'][:16]}] {x['content']}")
    time.sleep(0.6)

print(f"\n{replies} member(s) replied to the intro DM")
