#!/usr/bin/env python3
"""Unit tests for the Monday check-in mention picker.

    python3 -m pytest scripts/test_post_checkin.py      # if pytest is installed
    python3 scripts/test_post_checkin.py                # stdlib, no deps

Importing post_checkin must not need DISCORD_BOT_TOKEN or hit the network: if
that ever regresses, every test here fails at import.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import post_checkin as pc   # noqa: E402

NOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
ROLE = "1537836803275497562"        # App Leaders
TEAM = ["111", "222"]               # Adapty Team, Admin


def member(uid, hours_ago, roles=(ROLE,), bot=False, name=None):
    joined = NOW - timedelta(hours=hours_ago)
    return {"user": {"id": uid, "username": name or f"user{uid}", "bot": bot},
            "roles": list(roles),
            "joined_at": joined.isoformat()}


def pick(members, **kw):
    kw.setdefault("already_mentioned", set())
    return pc.pick_new_leaders(members, ROLE, TEAM, NOW, kw.pop("already_mentioned"), **kw)


def ids(picks):
    return [m["user"]["id"] for m in picks]


class PickNewLeaders(unittest.TestCase):

    def test_role_filter(self):
        members = [member("1", 48), member("2", 48, roles=["999"])]
        self.assertEqual(ids(pick(members)), ["1"])

    def test_bot_excluded(self):
        members = [member("1", 48), member("2", 48, bot=True)]
        self.assertEqual(ids(pick(members)), ["1"])

    def test_team_excluded(self):
        members = [member("1", 48),
                   member("2", 48, roles=[ROLE, "111"]),
                   member("3", 48, roles=[ROLE, "222"])]
        self.assertEqual(ids(pick(members)), ["1"])

    def test_window_edge(self):
        members = [member("in", 24 * 7 - 1), member("out", 24 * 8)]
        self.assertEqual(ids(pick(members)), ["in"])

    def test_min_age_edge(self):
        members = [member("young", 12), member("old-enough", 25)]
        self.assertEqual(ids(pick(members)), ["old-enough"])

    def test_already_mentioned_excluded(self):
        members = [member("1", 48), member("2", 30)]
        self.assertEqual(ids(pick(members, already_mentioned={"1"})), ["2"])

    def test_newest_first(self):
        members = [member("old", 120), member("new", 30), member("mid", 72)]
        self.assertEqual(ids(pick(members)), ["new", "mid", "old"])

    def test_cap_at_limit(self):
        members = [member(str(i), 30 + i) for i in range(12)]
        got = pick(members)
        self.assertEqual(len(got), 5)
        self.assertEqual(ids(got), ["0", "1", "2", "3", "4"])   # newest first
        self.assertEqual(len(pick(members, limit=2)), 2)

    def test_zero_picks(self):
        self.assertEqual(pick([]), [])
        self.assertEqual(pick([member("1", 2), member("2", 24 * 30)]), [])

    def test_custom_window_and_age(self):
        members = [member("a", 40), member("b", 60), member("c", 100)]
        self.assertEqual(ids(pick(members, window_days=3, min_age_hours=48)), ["b"])

    def test_tolerates_trailing_z_and_junk(self):
        m = member("1", 48)
        m["joined_at"] = m["joined_at"].replace("+00:00", "Z")
        broken = member("2", 48)
        broken["joined_at"] = "not a date"
        missing = member("3", 48)
        del missing["joined_at"]
        self.assertEqual(ids(pick([m, broken, missing])), ["1"])


class PreviousMentions(unittest.TestCase):

    def test_reads_only_our_own_checkins(self):
        msgs = [
            {"author": {"id": "bot"}, "content": "**monday check-in**\nhi",
             "mentions": [{"id": "a"}, {"id": "b"}]},
            {"author": {"id": "bot"}, "content": "some other bot post",
             "mentions": [{"id": "c"}]},
            {"author": {"id": "human"}, "content": "**monday check-in** fake",
             "mentions": [{"id": "d"}]},
            {"author": {"id": "bot"}, "content": "**monday check-in** again",
             "mentions": [{"id": "b"}, {"id": "e"}]},
        ]
        self.assertEqual(pc.previous_mentions(msgs, "bot"), {"a", "b", "e"})

    def test_empty(self):
        self.assertEqual(pc.previous_mentions([], "bot"), set())


TEMPLATE = ("**monday check-in**\n"
            "· what did you ship last week?\n"
            "one line is plenty. reply below 👇\n"
            "\n"
            "{new_leaders}\n")
LINE = "new app leaders this week, you go first 👋 {mentions}\n"


class Compose(unittest.TestCase):

    def test_with_picks(self):
        out = pc.compose(TEMPLATE, LINE, [member("1", 30), member("2", 40)])
        self.assertTrue(out.endswith(
            "new app leaders this week, you go first 👋 <@1> <@2>"))
        self.assertNotIn("{new_leaders}", out)
        self.assertNotIn("{mentions}", out)
        self.assertTrue(out.startswith("**monday check-in**"))

    def test_zero_picks_drops_the_line(self):
        out = pc.compose(TEMPLATE, LINE, [])
        self.assertNotIn("{new_leaders}", out)
        self.assertNotIn("new app leaders", out)
        self.assertFalse(out.endswith("\n"))
        self.assertEqual(out, "**monday check-in**\n"
                              "· what did you ship last week?\n"
                              "one line is plenty. reply below 👇")

    def test_real_copy_files_round_trip(self):
        root = Path(__file__).resolve().parent.parent
        template = (root / "checkin-message.md").read_text()
        line = (root / "checkin-new-leaders.md").read_text()
        self.assertIn("{new_leaders}", template)
        self.assertIn("{mentions}", line)
        empty = pc.compose(template, line, [])
        self.assertEqual(empty, template.split("\n{new_leaders}")[0].strip())
        full = pc.compose(template, line, [member("42", 30)])
        self.assertTrue(full.endswith("<@42>"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
