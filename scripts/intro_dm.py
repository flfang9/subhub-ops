"""DM members who joined 24-48h ago. Runs daily; window math makes each member eligible exactly once."""
import json, os, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

TOKEN = os.environ["DISCORD_BOT_TOKEN"].strip()
GUILD_ID = os.environ.get("GUILD_ID", "878003622917587034")
API = "https://discord.com/api/v10"

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": f"Bot {TOKEN}", "Content-Type": "application/json",
        "User-Agent": "DiscordBot (https://github.com/flfang9/subhub-ops, 1.0)"})
    with urllib.request.urlopen(r) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}

template = open("intro-dm.md").read().strip()
now = datetime.now(timezone.utc)
lo, hi = now - timedelta(hours=48), now - timedelta(hours=24)

members, after = [], "0"
while True:
    batch = req("GET", f"/guilds/{GUILD_ID}/members?limit=1000&after={after}")
    if not batch: break
    members += batch
    after = batch[-1]["user"]["id"]
    if len(batch) < 1000: break

targets = []
for m in members:
    if m["user"].get("bot"): continue
    joined = datetime.fromisoformat(m["joined_at"].replace("Z", "+00:00"))
    if lo <= joined < hi:
        targets.append(m)

print(f"{len(targets)} members joined 24-48h ago")
sent = failed = 0
for m in targets:
    name = m["user"].get("global_name") or m["user"]["username"]
    try:
        dm = req("POST", "/users/@me/channels", {"recipient_id": m["user"]["id"]})
        req("POST", f"/channels/{dm['id']}/messages", {"content": template.replace("{name}", name)})
        sent += 1
    except urllib.error.HTTPError as e:
        failed += 1  # DMs closed / privacy settings, expected for some
    time.sleep(1.5)
print(f"sent={sent} failed={failed}")
