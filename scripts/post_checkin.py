import json, os, sys, time, urllib.request

TOKEN = os.environ["DISCORD_BOT_TOKEN"].strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "1471517459617026162")  # building-in-public
API = "https://discord.com/api/v10"

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": f"Bot {TOKEN}", "Content-Type": "application/json",
        "User-Agent": "DiscordBot (https://github.com/flfang9/subhub-ops, 1.0)"})
    with urllib.request.urlopen(r) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}

content = open("checkin-message.md").read().strip()
msg = req("POST", f"/channels/{CHANNEL_ID}/messages", {"content": content})
print("posted message", msg["id"])

if os.environ.get("TEST_DELETE") == "true":
    time.sleep(2)
    req("DELETE", f"/channels/{CHANNEL_ID}/messages/{msg['id']}")
    print("test mode: deleted", msg["id"])
