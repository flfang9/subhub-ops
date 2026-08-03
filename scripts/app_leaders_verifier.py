"""App Leaders verification bot: watch MRR ticket channels, act on staff reactions.

Idempotent by latch: every control message this script posts carries an `[AL-VERIFY]`
embed footer, and the footer is edited to `done:approved` / `done:rejected` once acted on,
so re-running is always safe. NUDGE=1 also DMs pending applicants who never opened a ticket.
Needs scripts/app_leaders_config.json (written by app_leaders_migrate.py --execute).
"""
import json, os, time, urllib.parse, urllib.request, urllib.error

TOKEN = os.environ["DISCORD_BOT_TOKEN"].strip()
API = "https://discord.com/api/v10"
MARKER, NUDGE_MARKER = "[AL-VERIFY]", "[AL-NUDGE]"
OK, NO = "✅", "❌"
CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_leaders_config.json")

if not os.path.exists(CFG_PATH):
    print("no scripts/app_leaders_config.json — run app_leaders_migrate.py --execute first")
    raise SystemExit(0)
cfg = json.load(open(CFG_PATH))
GUILD, STAFF = cfg["guild_id"], set(cfg["staff_role_ids"])

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
            if e.code in (403, 404):
                return None  # no access to this ticket / DMs closed — caller counts it
            raise
    raise RuntimeError(f"rate-limited too long: {path}")

def write(method, path, body=None):
    out = req(method, path, body)
    time.sleep(0.5)
    return out

def display(user): return user.get("global_name") or user["username"]

def footer(msg):
    for e in msg.get("embeds") or []:
        text = (e.get("footer") or {}).get("text", "")
        if text.startswith(MARKER): return text
    return None

ME = req("GET", "/users/@me")["id"]
channels = req("GET", f"/guilds/{GUILD}/channels")
tickets = [c for c in channels if c["type"] == 0 and c.get("parent_id") == cfg["verification_category_id"]
           and c["name"].startswith("mrr-verification-") and c["id"] != cfg["log_channel_id"]]
print(f"{len(tickets)} ticket channel(s) under the verification category")

welcome_copy = open("welcome-app-leader.md").read().strip()
reject_copy = open("reject-app-leader.md").read().strip()

def applicant_of(ch, msgs):
    """The one human member-type (1) overwrite that isn't this bot; else earliest non-bot author."""
    ids = [o["id"] for o in ch.get("permission_overwrites", []) if str(o.get("type")) in ("1", "member") and o["id"] != ME]
    if len(ids) > 1:  # Dyno adds itself as a member overwrite on its tickets — drop bot accounts
        ids = [i for i in ids if not (req("GET", f"/users/{i}") or {}).get("bot")]
    if len(ids) == 1: return ids[0]
    for m in sorted(msgs or [], key=lambda m: m["timestamp"]):
        if not m["author"].get("bot"): return m["author"]["id"]
    return None

def staff_verdict(cid, mid):
    """First staff reactor wins; a staff ✅ beats a staff ❌ on the same message."""
    for emoji, verdict in ((OK, "approve"), (NO, "reject")):
        users = req("GET", f"/channels/{cid}/messages/{mid}/reactions/{urllib.parse.quote(emoji)}?limit=100") or []
        for u in users:
            if u["id"] == ME or u.get("bot"): continue
            m = req("GET", f"/guilds/{GUILD}/members/{u['id']}")
            if m and set(m["roles"]) & STAFF: return verdict, display(u)
    return None, None

def close(ch, msg, verdict):
    e = dict((msg.get("embeds") or [{}])[0])
    e["footer"] = {"text": f"{MARKER} done:{verdict}"}
    write("PATCH", f"/channels/{ch['id']}/messages/{msg['id']}", {"embeds": [e]})

seen_applicants = set()
for ch in tickets:
    msgs = req("GET", f"/channels/{ch['id']}/messages?limit=50")
    if msgs is None:
        print(f"  #{ch['name']}: 403 — no access, skipped")
        bump("skipped_403")
        continue
    bump("tickets_seen")
    uid = applicant_of(ch, msgs)
    if uid: seen_applicants.add(uid)
    decision = next((m for m in msgs if m["author"]["id"] == ME and footer(m)), None)

    if not decision:
        posted = write("POST", f"/channels/{ch['id']}/messages", {"embeds": [{
            "title": "App Leaders verification", "color": 0xE8B54D,
            "description": ("Post below: **app name**, **App Store / Play link**, and a **screenshot of your MRR**"
                            " (App Store Connect, Play Console, RevenueCat, Adapty — whatever you use).\n"
                            "This ticket is private: staff only, never shared publicly.\n\n"
                            f"**Staff:** react {OK} on this message to approve, {NO} to reject."),
            "footer": {"text": f"{MARKER} open"}}]})
        if posted:
            for emoji in (OK, NO):
                write("PUT", f"/channels/{ch['id']}/messages/{posted['id']}/reactions/{urllib.parse.quote(emoji)}/@me")
        print(f"  #{ch['name']}: decision message posted")
        bump("decisions_posted")
        continue

    if not footer(decision).endswith("open"):
        bump("already_done")
        continue
    verdict, staff_name = staff_verdict(ch["id"], decision["id"])
    if not verdict:
        print(f"  #{ch['name']}: awaiting staff reaction")
        bump("awaiting")
        continue
    if not uid:
        print(f"  #{ch['name']}: {verdict} but applicant unidentifiable — left open")
        bump("no_applicant")
        continue

    member = req("GET", f"/guilds/{GUILD}/members/{uid}") or {}
    name = display(member.get("user", {"username": uid}))
    if verdict == "approve":
        write("PUT", f"/guilds/{GUILD}/members/{uid}/roles/{cfg['app_leaders_role_id']}")
        write("DELETE", f"/guilds/{GUILD}/members/{uid}/roles/{cfg['pending_role_id']}")
        write("POST", f"/channels/{cfg['app_leaders_channel_id']}/messages",
              {"content": welcome_copy.replace("{mention}", f"<@{uid}>").replace("{name}", name)})
        write("POST", f"/channels/{cfg['log_channel_id']}/messages",
              {"content": f"{OK} {name} approved for App Leaders by {staff_name}"})
        write("POST", f"/channels/{ch['id']}/messages",
              {"content": f"{OK} verified — you're in. See <#{cfg['app_leaders_channel_id']}>."})
        close(ch, decision, "approved")
        print(f"  #{ch['name']}: APPROVED {name} (by {staff_name})")
        bump("approved")
    else:
        write("DELETE", f"/guilds/{GUILD}/members/{uid}/roles/{cfg['pending_role_id']}")
        write("POST", f"/channels/{ch['id']}/messages", {"content": reject_copy.replace("{name}", name)})
        write("POST", f"/channels/{cfg['log_channel_id']}/messages",
              {"content": f"{NO} {name} not verified for App Leaders (by {staff_name})"})
        close(ch, decision, "rejected")
        print(f"  #{ch['name']}: REJECTED {name} (by {staff_name})")
        bump("rejected")

if os.environ.get("NUDGE") == "1" and n.get("skipped_403"):
    print("nudge sweep skipped: unreadable (403) tickets make the applicant map incomplete")
elif os.environ.get("NUDGE") == "1":
    nudge_copy = open("nudge-app-leaders.md").read().strip()
    members, after = [], "0"
    while True:
        batch = req("GET", f"/guilds/{GUILD}/members?limit=1000&after={after}")
        if not batch: break
        members += batch
        after = batch[-1]["user"]["id"]
        if len(batch) < 1000: break
    stale = [m for m in members if cfg["pending_role_id"] in m["roles"]
             and not m["user"].get("bot") and m["user"]["id"] not in seen_applicants]
    print(f"nudge sweep: {len(stale)} pending member(s) with no ticket")
    for m in stale:
        uid, name = m["user"]["id"], display(m["user"])
        dm = req("POST", "/users/@me/channels", {"recipient_id": uid})
        if not dm:
            bump("nudge_failed")
            continue
        prior = req("GET", f"/channels/{dm['id']}/messages?limit=20") or []
        if sum(1 for x in prior if x["author"]["id"] == ME and NUDGE_MARKER in x["content"]) >= 2:
            bump("nudge_maxed")
            continue
        sent = req("POST", f"/channels/{dm['id']}/messages", {"content": nudge_copy.replace("{name}", name)})
        bump("nudges_sent" if sent else "nudge_failed")
        time.sleep(1.0)

print("\n=== run summary ===")
for k in sorted(n): print(f"  {k}: {n[k]}")
