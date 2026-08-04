"""One-time migration: MRR Clubs -> App Leaders.

Dry-run by default (prints every write it would make, touches nothing).
Run locally:
  DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/app_leaders_migrate.py
  DISCORD_BOT_TOKEN=$(cat ~/.config/discord-audit/token) python3 scripts/app_leaders_migrate.py --execute
Order under --execute: create role -> grant -> rename pending -> channels -> post copy -> delete old roles.
"""
import json, os, sys, time, urllib.request, urllib.error

TOKEN = os.environ["DISCORD_BOT_TOKEN"].strip()
GUILD_ID = os.environ.get("GUILD_ID", "878003622917587034")
API = "https://discord.com/api/v10"
EXECUTE = "--execute" in sys.argv

PENDING_ROLE = "1513624140240650392"          # MRR Verification Pending -> App Leaders (Pending)
CLAIM_ROLES = ["1513624233509392525",          # MRR Claim: Five Figures Club
               "1513624341470773348"]          # MRR Claim: Six Figures Club
VERIFIED_ROLES = ["1513624463617294458",       # Five Figures Club (Verified MRR 10k+)
                  "1513624434026745946"]       # Six Figures Club (Verified MRR 100k+)
STAFF_ROLES = ["956444916194611230", "940245057452265512"]  # Adapty Team, Admin
BOT_ROLE = "1523751839672303820"               # SubHub Audit (this bot)
LOG_CHANNEL = "1513664526086574212"            # #mrr-verification-log
JOIN_CHANNEL = "1513625158454349964"           # #unlock-private-club -> #join-app-leaders
INTROS_CHANNEL = "1513625530291851445"         # #intros -> #app-leaders
OFFICE_HOURS_VC = "1516239450198249653"        # stays in the club category
TO_ARCHIVE = ["1513625622780317846",           # #growth
              "1513625759061905590",           # #wins
              "1516239775965646868",           # six-figures voice
              "1513626158879739924", "1513626249736618135", "1513626465822965760"]
VIEW_CHANNEL = 0x400
NEW_ROLE = {"name": "App Leaders", "hoist": True, "mentionable": False, "color": 0xE8B54D}

n = {}
def bump(k): n[k] = n.get(k, 0) + 1

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
            raise
    raise RuntimeError(f"rate-limited too long: {path}")

def act(kind, label, method, path, body=None):
    """Print the action; only write under --execute. 403/404 = skip + count, never crash."""
    print(("  EXEC  " if EXECUTE else "  DRY   ") + label)
    bump(kind)
    if not EXECUTE:
        return None
    try:
        out = req(method, path, body)
    except urllib.error.HTTPError as e:
        print(f"        !! HTTP {e.code}, skipped")
        bump(f"failed:{e.code}")
        return None
    time.sleep(0.5)
    return out

print("=== App Leaders migration:", "EXECUTE" if EXECUTE else "DRY RUN (no writes)", "===\n")

roles = {r["id"]: r for r in req("GET", f"/guilds/{GUILD_ID}/roles")}
channels = {c["id"]: c for c in req("GET", f"/guilds/{GUILD_ID}/channels")}
rname = lambda rid: roles.get(rid, {}).get("name", f"<unknown {rid}>")
cname = lambda cid: channels.get(cid, {}).get("name", f"<unknown {cid}>")

members, after = [], "0"
while True:
    batch = req("GET", f"/guilds/{GUILD_ID}/members?limit=1000&after={after}")
    if not batch: break
    members += batch
    after = batch[-1]["user"]["id"]
    if len(batch) < 1000: break
print(f"{len(members)} members scanned")
for rid in [PENDING_ROLE] + CLAIM_ROLES + VERIFIED_ROLES:
    print(f"  {rname(rid)}: {sum(1 for m in members if rid in m['roles'])} holders")

cats = [c for c in channels.values() if c["type"] == 4]
five_cat = next((c for c in cats if c["name"].startswith("Five Figures Club")), None)
six_cat = next((c for c in cats if c["name"].startswith("Six Figures Club")), None)
archive_cat = next((c for c in cats if "ARCHIVE" in c["name"].upper()), None)
verification_cat = channels.get(LOG_CHANNEL, {}).get("parent_id")
for label, c in [("club category", five_cat), ("six-figures category", six_cat), ("archive", archive_cat)]:
    print(f"  {label}: {c['name'] + ' ' + c['id'] if c else 'NOT FOUND'}")
print(f"  verification category: {verification_cat}\n")

# 1. create the App Leaders role
print("[1] role: create")
new = act("role_create", f"create role {NEW_ROLE['name']} (hoist, color #E8B54D)",
          "POST", f"/guilds/{GUILD_ID}/roles", NEW_ROLE)
app_leaders_role = new["id"] if new else "<new-app-leaders-role-id>"
print(f"        -> {app_leaders_role}")

cfg = {"app_leaders_role_id": app_leaders_role, "pending_role_id": PENDING_ROLE, "guild_id": GUILD_ID,
       "app_leaders_channel_id": INTROS_CHANNEL, "log_channel_id": LOG_CHANNEL,
       "staff_role_ids": STAFF_ROLES, "verification_category_id": verification_cat}
cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_leaders_config.json")
if EXECUTE:
    open(cfg_path, "w").write(json.dumps(cfg, indent=2) + "\n")
    print(f"        wrote {cfg_path}")
else:
    print("        would write scripts/app_leaders_config.json:")
    print("        " + json.dumps(cfg, indent=2).replace("\n", "\n        "))

# 2. grant the new role to already-verified holders
print("\n[2] role: grant to verified holders")
holders = [m for m in members if set(m["roles"]) & set(VERIFIED_ROLES)]
for m in holders:
    name = m["user"].get("global_name") or m["user"]["username"]
    act("granted", f"grant App Leaders to {name} (@{m['user']['username']})",
        "PUT", f"/guilds/{GUILD_ID}/members/{m['user']['id']}/roles/{app_leaders_role}")
if not holders: print("  (no verified holders)")

# 3. rename the pending role
print("\n[3] role: rename pending")
act("role_rename", f"rename '{rname(PENDING_ROLE)}' -> 'App Leaders (Pending)'",
    "PATCH", f"/guilds/{GUILD_ID}/roles/{PENDING_ROLE}", {"name": "App Leaders (Pending)"})

# 4. channels
print("\n[4] channels")
if five_cat:
    act("ch_rename", f"rename category '{five_cat['name']}' -> '💎 App Leaders'",
        "PATCH", f"/channels/{five_cat['id']}", {"name": "💎 App Leaders"})
act("ch_rename", f"rename #{cname(INTROS_CHANNEL)} -> #app-leaders",
    "PATCH", f"/channels/{INTROS_CHANNEL}", {"name": "app-leaders"})
act("ch_rename", f"rename #{cname(JOIN_CHANNEL)} -> #join-app-leaders",
    "PATCH", f"/channels/{JOIN_CHANNEL}", {"name": "join-app-leaders"})
if archive_cat:
    for cid in TO_ARCHIVE:
        act("ch_move", f"move #{cname(cid)} -> {archive_cat['name']}",
            "PATCH", f"/channels/{cid}", {"parent_id": archive_cat["id"]})
else:
    print("  !! no ARCHIVE category found, skipping all moves")
    bump("failed:no-archive")

print("  permission overwrites (private club):")
allow_roles = [(app_leaders_role, "App Leaders"), (STAFF_ROLES[0], "Adapty Team"),
               (STAFF_ROLES[1], "Admin"), (BOT_ROLE, "SubHub Audit")]
for cid, label in [(five_cat["id"] if five_cat else None, "💎 App Leaders category"),
                   (INTROS_CHANNEL, "#app-leaders"), (OFFICE_HOURS_VC, "office-hours voice")]:
    if not cid: continue
    act("overwrite", f"deny VIEW_CHANNEL to @everyone on {label}",
        "PUT", f"/channels/{cid}/permissions/{GUILD_ID}", {"type": 0, "deny": str(VIEW_CHANNEL)})
    for rid, label_r in allow_roles:
        act("overwrite", f"allow VIEW_CHANNEL to {label_r} on {label}",
            "PUT", f"/channels/{cid}/permissions/{rid}", {"type": 0, "allow": str(VIEW_CHANNEL)})

if six_cat and archive_cat:
    act("ch_delete", f"delete now-empty category '{six_cat['name']}'", "DELETE", f"/channels/{six_cat['id']}")
elif six_cat:
    print(f"  !! keeping '{six_cat['name']}', no ARCHIVE category, its channels were not moved")

# 5. post the join copy
print("\n[5] copy")
join_copy = open("join-app-leaders.md").read().strip()
act("posted", f"post join-app-leaders.md ({len(join_copy)} chars) to #join-app-leaders",
    "POST", f"/channels/{JOIN_CHANNEL}/messages", {"content": join_copy})

# 6. delete the old roles LAST
print("\n[6] roles: delete old")
for rid in CLAIM_ROLES + VERIFIED_ROLES:
    act("role_delete", f"delete role '{rname(rid)}' ({sum(1 for m in members if rid in m['roles'])} holders)",
        "DELETE", f"/guilds/{GUILD_ID}/roles/{rid}")

print("\n=== report ===")
for k in sorted(n): print(f"  {k}: {n[k]}")
if not EXECUTE: print("\ndry run, nothing was written. re-run with --execute to apply.")
