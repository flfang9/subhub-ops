"""Re-add the country question as a Channels & Roles-only prompt (NOT in the join flow).

Builds a "Where are you based?" prompt from the existing country roles with flag emoji,
in_onboarding=False so it only appears in the server's Channels & Roles tab.
The onboarding PUT replaces the ENTIRE prompts array, so this script GETs the current
config, backs it up to ~/.config/discord-audit/, and appends/replaces only this prompt.
Needs the bot to have Manage Guild + Manage Roles.

Dry-run by default:
  DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/set_country_prompt.py
  DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/set_country_prompt.py --execute
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import date
from pathlib import Path

TOKEN = os.environ["DISCORD_BOT_TOKEN"].strip()
GUILD_ID = os.environ.get("GUILD_ID", "878003622917587034")
API = "https://discord.com/api/v10"
EXECUTE = "--execute" in sys.argv
PROMPT_TITLE = "Where are you based?"

# role name (exact) -> ISO2 for the flag emoji; OTHER_COUNTRY handled below
ISO = {"USA": "US", "India": "IN", "UK": "GB", "Ukraine": "UA", "Poland": "PL",
       "Netherlands": "NL", "Italy": "IT", "Brazil": "BR", "Australia": "AU", "Spain": "ES",
       "Sweden": "SE", "Czech Republic": "CZ", "Austria": "AT", "Romania": "RO", "Denmark": "DK",
       "Israel": "IL", "Turkey": "TR", "Portugal": "PT", "New Zealand": "NZ", "Finland": "FI",
       "Greece": "GR", "South Africa": "ZA", "Bulgaria": "BG", "Pakistan": "PK", "Norway": "NO",
       "Hungary": "HU", "Ireland": "IE", "Colombia": "CO", "Russia": "RU", "Lithuania": "LT",
       "Japan": "JP", "Indonesia": "ID", "Serbia": "RS", "Estonia": "EE", "Slovakia": "SK",
       "Vietnam": "VN", "Egypt": "EG", "Chile": "CL", "Thailand": "TH", "Singapore": "SG",
       "South Korea": "KR", "Switzerland": "CH", "UAE": "AE"}

def flag(iso):
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso)

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
            print(f"HTTP {e.code} on {method} {path}: {e.read().decode()[:400]}")
            raise
    raise RuntimeError(f"rate-limited too long: {path}")

roles = req("GET", f"/guilds/{GUILD_ID}/roles")
by_name = {r["name"]: r for r in roles}

options, missing = [], []
for name, iso in sorted(ISO.items()):
    if name not in by_name:
        missing.append(name)
        continue
    options.append({"id": str(len(options) + 1), "title": name, "description": "",
                    "emoji_name": flag(iso), "role_ids": [by_name[name]["id"]], "channel_ids": []})
if "OTHER_COUNTRY" in by_name:
    options.append({"id": str(len(options) + 1), "title": "Other country", "description": "",
                    "emoji_name": "🌍", "role_ids": [by_name["OTHER_COUNTRY"]["id"]], "channel_ids": []})
else:
    missing.append("OTHER_COUNTRY")
print(f"{len(options)} country options built" + (f"; MISSING roles: {missing}" if missing else ""))

# role icons: flag shows next to the member's name in chat (server is boost tier 3).
# needs the bot's role dragged ABOVE the country roles (they sit up to position ~121).
print("\nrole icons:")
icons = [(n, flag(i)) for n, i in sorted(ISO.items())] + [("OTHER_COUNTRY", "🌍")]
for name, emoji in icons:
    r = by_name.get(name)
    if not r:
        continue
    if r.get("unicode_emoji") == emoji:
        continue  # already set, keep re-runs quiet
    print(f"  {'set' if EXECUTE else 'would set'} {emoji} on role '{name}'")
    if EXECUTE:
        try:
            req("PATCH", f"/guilds/{GUILD_ID}/roles/{r['id']}", {"unicode_emoji": emoji})
            time.sleep(0.5)
        except urllib.error.HTTPError:
            print(f"  !! failed on '{name}' (is the bot's role above the country roles?)")

ob = req("GET", f"/guilds/{GUILD_ID}/onboarding")
backup = Path.home() / ".config" / "discord-audit" / f"onboarding-backup-{date.today()}.json"
backup.write_text(json.dumps(ob, indent=2))
print(f"current onboarding backed up -> {backup}")

kept = [p for p in ob["prompts"] if p["title"].strip() != PROMPT_TITLE]
if len(kept) < len(ob["prompts"]):
    print(f"replacing existing '{PROMPT_TITLE}' prompt")
country_prompt = {"id": "0", "type": 0, "title": PROMPT_TITLE, "options": options,
                  "single_select": True, "required": False, "in_onboarding": False}
payload = {"prompts": kept + [country_prompt], "enabled": ob["enabled"],
           "default_channel_ids": ob["default_channel_ids"], "mode": ob["mode"]}

print(f"prompts after: {[p['title'] for p in payload['prompts']]}")
if not EXECUTE:
    print("\ndry run, nothing written. re-run with --execute to apply.")
    raise SystemExit(0)

req("PUT", f"/guilds/{GUILD_ID}/onboarding", payload)
check = req("GET", f"/guilds/{GUILD_ID}/onboarding")
got = next((p for p in check["prompts"] if p["title"].strip() == PROMPT_TITLE), None)
if got and len(got["options"]) == len(options) and not got["in_onboarding"]:
    print(f"OK, '{PROMPT_TITLE}' live with {len(got['options'])} options, "
          "hidden from the join flow (Channels & Roles tab only)")
else:
    print("!! verify failed, check Server Settings -> Onboarding; "
          f"restore from {backup} if the prompt list looks wrong")
