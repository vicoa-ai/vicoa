"""Tests for snapshot.py. Run: python3 -m unittest discover -s examples/plugins/dashboard/tests"""

import datetime
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location(
    "snapshot", os.path.join(PLUGIN, "snapshot.py")
)
assert spec is not None and spec.loader is not None
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)

NOW = datetime.datetime(2026, 11, 11, 4, 0, tzinfo=datetime.timezone.utc)

GOOD = {
    "headline": {
        "label": "Revenue, 30 d",
        "value": "$18,300",
        "tag": "partial",
        "note": "iOS and web; Android not read yet",
        "asOf": "2026-11-07",
        "goal": {"label": "$40k/month", "progress": 0.46, "by": "2027-06-30"},
    },
    "metrics": [
        {"label": "Paying users", "value": "1,420", "asOf": "2026-11-07"},
        {
            "label": "Signups, 30 d",
            "value": None,
            "note": "Store report not out yet",
            "asOf": "2026-11-10",
        },
    ],
    "flags": [{"text": "Certificate expires in 12 days", "tone": "warn"}],
}


def run(argv, payload=None):
    out, err = io.StringIO(), io.StringIO()
    stdin = io.StringIO(json.dumps(payload) if payload is not None else "")
    with redirect_stdout(out), redirect_stderr(err):
        code = snapshot.main(argv, stdin=stdin)
    return code, out.getvalue(), err.getvalue()


class Validate(unittest.TestCase):
    def problems(self, doc):
        return snapshot.validate(doc, NOW)

    def test_good_payload_passes(self):
        self.assertEqual(self.problems(GOOD), [])

    def test_sample_in_the_readme_folder_passes(self):
        with open(os.path.join(PLUGIN, "sample-snapshot.json"), encoding="utf-8") as f:
            sample = json.load(f)
        sent = {k: v for k, v in sample.items() if k not in snapshot.STAMPED_KEYS}
        self.assertEqual(snapshot.validate(sent, NOW), [])

    def test_prose_is_refused(self):
        doc = json.loads(json.dumps(GOOD))
        doc["headline"]["note"] = (
            "Everything sold in the last 30 days across both stores and the website, after refunds, before fees"
        )
        p = self.problems(doc)
        self.assertEqual(len(p), 1)
        self.assertIn("headline.note", p[0])
        self.assertIn("at most 80", p[0])

    def test_unknown_must_be_null_with_a_reason(self):
        for value in ("unknown", "Unknown (billing API down)"):
            p = self.problems(
                {"metrics": [{"label": "Paying", "value": value, "asOf": "2026-11-10"}]}
            )
            self.assertTrue(any("use null" in x for x in p), p)
        p = self.problems(
            {"metrics": [{"label": "Paying", "value": None, "asOf": "2026-11-10"}]}
        )
        self.assertTrue(any("metrics[0].note" in x and "why" in x for x in p), p)

    def test_numbers_must_be_text_with_their_unit(self):
        p = self.problems(
            {"metrics": [{"label": "Paying", "value": 1420, "asOf": "2026-11-10"}]}
        )
        self.assertTrue(any("as text" in x for x in p), p)

    def test_as_of_required_well_formed_and_not_ahead(self):
        self.assertTrue(
            any(
                "required" in x
                for x in self.problems({"metrics": [{"label": "A", "value": "1"}]})
            )
        )
        self.assertTrue(
            any(
                "not YYYY-MM-DD" in x
                for x in self.problems(
                    {"metrics": [{"label": "A", "value": "1", "asOf": "Nov 8"}]}
                )
            )
        )
        self.assertTrue(
            any(
                "no zone" in x or "with a zone" in x
                for x in self.problems(
                    {
                        "metrics": [
                            {"label": "A", "value": "1", "asOf": "2026-11-08T08:00:00"}
                        ]
                    }
                )
            )
        )
        self.assertTrue(
            any(
                "future" in x
                for x in self.problems(
                    {"metrics": [{"label": "A", "value": "1", "asOf": "2026-11-20"}]}
                )
            )
        )
        # Late in the UTC day it is already tomorrow in zones ahead of UTC: that date is fine.
        late = datetime.datetime(2026, 11, 11, 20, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(
            snapshot.validate(
                {"metrics": [{"label": "A", "value": "1", "asOf": "2026-11-12"}]}, late
            ),
            [],
        )

    def test_old_format_keys_are_named(self):
        p = self.problems({"asOf": "2026-11-08", "card": {}})
        self.assertTrue(any(x.startswith("asOf:") and "each metric" in x for x in p), p)
        self.assertTrue(any(x.startswith("card:") for x in p), p)

    def test_enums_limits_and_goal(self):
        doc = {
            "headline": {
                "label": "R",
                "value": "$1",
                "tag": "rough",
                "asOf": "2026-11-08",
                "goal": {"label": "$5k", "progress": 6, "by": "Dec 31"},
            },
            "flags": [{"text": "x", "tone": "red"}] * 7,
        }
        p = "\n".join(self.problems(doc))
        for want in (
            "headline.tag",
            "goal.progress",
            "goal.by",
            "flags: 7 entries",
            "flags[0].tone",
        ):
            self.assertIn(want, p)

    def test_lane_rules_must_compile(self):
        p = self.problems(
            {
                "laneRules": [
                    {"lane": "build", "match": "(dev"},
                    {"lane": "misc", "match": "x"},
                ]
            }
        )
        self.assertTrue(any("not a regular expression" in x for x in p), p)
        self.assertTrue(any("laneRules[1].lane" in x for x in p), p)


class Write(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.path = os.path.join(self.dir, ".vicoa", "dashboard.local.json")

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_write_stamps_and_describes(self):
        code, out, err = run(["write", "--dir", self.dir, "--by", "testbot"], GOOD)
        self.assertEqual(code, 0, err)
        doc = self.read()
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["updatedBy"], "testbot")
        self.assertRegex(doc["updatedAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(list(doc)[:3], ["version", "updatedAt", "updatedBy"])
        self.assertIn("$18,300 (partial) · 46% of $40k/month, by Jun 30", out)
        self.assertIn("Unknown · Store report not out yet", out)

    def test_refused_write_changes_nothing(self):
        run(["write", "--dir", self.dir], GOOD)
        before = self.read()
        code, _, err = run(
            ["write", "--dir", self.dir], {"headline": {"label": "R", "value": 5}}
        )
        self.assertEqual(code, 2)
        self.assertIn("refused, nothing written", err)
        self.assertEqual(self.read(), before)

    def test_numbers_are_one_set_and_the_rest_is_kept(self):
        rules = [{"lane": "build", "match": "dev"}]
        run(["write", "--dir", self.dir], dict(GOOD, laneRules=rules, staleAfterDays=5))
        # Numbers only: the flag that wasn't sent again is gone, the rules stay.
        run(["write", "--dir", self.dir], {"headline": GOOD["headline"]})
        doc = self.read()
        self.assertNotIn("flags", doc)
        self.assertNotIn("metrics", doc)
        self.assertEqual(doc["laneRules"], rules)
        self.assertEqual(doc["staleAfterDays"], 5)
        # No numbers sent: the numbers stay. null removes a kept key.
        run(
            ["write", "--dir", self.dir],
            {"build": {"summary": "2.3 in review"}, "staleAfterDays": None},
        )
        doc = self.read()
        self.assertEqual(doc["headline"]["value"], "$18,300")
        self.assertEqual(doc["build"]["summary"], "2.3 in review")
        self.assertNotIn("staleAfterDays", doc)

    def test_older_file_keeps_its_rules_and_drops_its_numbers(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "asOf": "2026-11-08",
                    "headline": {"label": "Old", "value": "$1"},
                    "card": {},
                    "laneRules": [{"lane": "ops", "match": "ops"}],
                },
                f,
            )
        run(["write", "--dir", self.dir], {"build": {"summary": "x"}})
        doc = self.read()
        self.assertNotIn("headline", doc)
        self.assertNotIn("card", doc)
        self.assertNotIn("asOf", doc)
        self.assertEqual(doc["laneRules"], [{"lane": "ops", "match": "ops"}])

    def test_stamped_keys_sent_back_are_ignored(self):
        run(["write", "--dir", self.dir, "--by", "a"], GOOD)
        doc = self.read()
        doc["updatedAt"] = "2020-01-01T00:00:00Z"
        code, _, err = run(["write", "--dir", self.dir, "--by", "b"], doc)
        self.assertEqual(code, 0, err)
        self.assertNotEqual(self.read()["updatedAt"], "2020-01-01T00:00:00Z")
        self.assertEqual(self.read()["updatedBy"], "b")

    def test_keeps_the_file_out_of_git_once(self):
        subprocess.run(["git", "init", "-q", self.dir], check=True)
        _, out, _ = run(["write", "--dir", self.dir], GOOD)
        self.assertIn("added .vicoa/*.local.json", out)
        _, out, _ = run(["write", "--dir", self.dir], GOOD)
        self.assertNotIn("added", out)
        with open(
            os.path.join(self.dir, ".git", "info", "exclude"), encoding="utf-8"
        ) as f:
            self.assertEqual(f.read().count(".vicoa/*.local.json"), 1)
        status = subprocess.run(
            ["git", "-C", self.dir, "status", "--porcelain"],
            capture_output=True,
            text=True,
        ).stdout
        self.assertEqual(status.strip(), "")

    def test_check(self):
        code, out, _ = run(["check", "--dir", self.dir])
        self.assertEqual(code, 1)
        self.assertIn("no snapshot", out)
        run(["write", "--dir", self.dir, "--by", "testbot"], GOOD)
        code, out, _ = run(["check", "--dir", self.dir])
        self.assertEqual(code, 0, out)
        self.assertIn("by testbot", out)
        self.assertNotIn("stale", out)
        doc = self.read()
        doc["updatedAt"] = "2026-11-01T00:00:00Z"
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        _, out, _ = run(["check", "--dir", self.dir])
        self.assertIn("stale: not updated for", out)


if __name__ == "__main__":
    unittest.main()
