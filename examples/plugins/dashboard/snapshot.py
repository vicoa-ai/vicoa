#!/usr/bin/env python3
"""Write or check a project's Dashboard snapshot, the numbers the Dashboard plugin shows.

usage:
  python3 snapshot.py write [--dir PROJECT_DIR] [--by NAME] [--file FILE]   (JSON on stdin unless --file)
  python3 snapshot.py check [--dir PROJECT_DIR]

The file is PROJECT_DIR/.vicoa/dashboard.local.json (default: the current folder). `write` checks what you send
against the rules below and refuses it, listing every problem, if any rule is broken; otherwise it keeps what it
doesn't replace, stamps the time and writes the file in one step. It also keeps the file out of git: numbers like
revenue don't belong in a repository.

What to send (every key optional):

  {
    "headline": {"label": "Revenue, 30 d", "value": "$18,300", "tag": "partial",
                 "note": "iOS and web; Android not read yet", "asOf": "2026-11-07",
                 "goal": {"label": "$40k/month", "progress": 0.46, "by": "2027-06-30"}},
    "metrics":  [{"label": "Paying users", "value": "1,420", "note": "85 new this week", "asOf": "2026-11-07"}],
    "flags":    [{"text": "Certificate expires in 12 days", "tone": "warn"}]
  }

  value    The figure with its unit, as text: "$18,300", "~2,300", "1,420". At most 16 characters. If you couldn't
           read it: null, with the reason in note. Never 0 for a number you don't have.
  note     What the number covers, in at most 80 characters. The page has one line for it; the full caveats
           belong in your own notes, not here.
  tag      "partial" (a channel it should cover is missing, e.g. Android not read) or "estimate" (approximated).
           Otherwise leave it out.
  asOf     The last day the number covers: YYYY-MM-DD, or an ISO time with its zone. Required.
  label    At most 32 characters. The headline is the project's card on the overview; give every project's
           headline the same label so the cards compare.
  goal     label (at most 24 characters), progress from 0 to 1 on the target's own definition, by: YYYY-MM-DD.
  metrics  At most 6, shown in the order sent, each like the headline without goal.
  flags    At most 6, shown under Watch: only what someone should act on, not a repeat of an Unknown above.
           tone: good, warn, bad or info (default warn). text at most 80 characters, detail at most 120.

headline, metrics and flags are one set: a write that sends any of them replaces all three, so a metric or a
flag you stop sending disappears. build, growth, ops, laneRules and staleAfterDays are kept until you send them
(null removes one); the plugin's README describes them. version, updatedAt and updatedBy are stamped here.

Python 3.9+, standard library only.
"""

import argparse
import datetime
import json
import math
import os
import re
import subprocess
import sys

VERSION = 1
OUT_REL = os.path.join(".vicoa", "dashboard.local.json")
EXCLUDE_LINE = ".vicoa/*.local.json"

NUMBER_KEYS = ("headline", "metrics", "flags")  # replaced together
KEPT_KEYS = ("build", "growth", "ops", "laneRules", "staleAfterDays")  # kept until sent
STAMPED_KEYS = (
    "version",
    "updatedAt",
    "updatedBy",
)  # written by this command; ignored when sent
ORDER = STAMPED_KEYS + NUMBER_KEYS + KEPT_KEYS

TONES = ("good", "warn", "bad", "info", "neutral")
TAGS = ("partial", "estimate")
STATES = ("done", "active", "waiting", "paused", "risk", "blocked", "todo")
LANES = ("build", "growth", "ops")
LAYOUTS = ("row", "list")

MAX = {
    "label": 32,
    "value": 16,
    "note": 80,
    "goal": 24,
    "flag": 80,
    "detail": 120,
    "metrics": 6,
    "flags": 6,
    "series": 60,
    "summary": 80,
    "group": 40,
    "aside": 24,
    "groups": 6,
    "items": 12,
    "item": 60,
    "date": 16,
    "ops": 6,
    "rules": 20,
    "match": 200,
}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]
UTC = datetime.timezone.utc


class Problems(list):
    def add(self, path, message):
        self.append("%s: %s" % (path, message))


def _text(p, path, v, limit, required=False):
    if v is None:
        if required:
            p.add(path, "required")
        return
    if not isinstance(v, str):
        p.add(path, "must be text")
    elif not v.strip():
        p.add(
            path,
            "empty; leave it out" + (" or use null" if path.endswith(".value") else ""),
        )
    elif "\n" in v:
        p.add(path, "must be one line")
    elif len(v) > limit:
        p.add(
            path,
            "%d characters, at most %d: %r"
            % (len(v), limit, v[:48] + ("…" if len(v) > 48 else "")),
        )


def _keys(p, path, obj, allowed):
    extra = sorted(set(obj) - set(allowed))
    if extra:
        p.add(
            path,
            "unknown key%s %s (allowed: %s)"
            % ("s" if len(extra) > 1 else "", ", ".join(extra), ", ".join(allowed)),
        )


def parse_time(v):
    """A date ("2026-11-08", taken as the end of that day in UTC) or an ISO time with a zone, as an aware datetime."""
    if _DATE.match(v):
        d = datetime.date.fromisoformat(v)
        return datetime.datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=UTC)
    t = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("no time zone")
    return t


def _as_of(p, path, v, now):
    if v is None:
        p.add(path, "required: the last day the number covers, YYYY-MM-DD")
        return
    if not isinstance(v, str):
        p.add(path, "must be text, YYYY-MM-DD")
        return
    try:
        t = parse_time(v)
    except ValueError:
        p.add(path, "%r is not YYYY-MM-DD or an ISO time with a zone" % v)
        return
    # A date in a zone ahead of UTC can be "tomorrow" for a few hours; anything later is a mistake.
    if t - now > datetime.timedelta(days=1, hours=14):
        p.add(path, "%s is in the future" % v)


def _figure(p, path, m, now, goal):
    if not isinstance(m, dict):
        p.add(path, "must be an object")
        return
    _keys(
        p,
        path,
        m,
        ("label", "value", "tag", "note", "asOf", "series")
        + (("goal",) if goal else ()),
    )
    _text(p, path + ".label", m.get("label"), MAX["label"], required=True)
    if "value" not in m:
        p.add(path + ".value", "required (null if you couldn't read it)")
    v = m.get("value")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        p.add(
            path + ".value",
            'write it as text with its unit, like "%s" or "$%s"' % (v, v),
        )
    elif v is not None:
        _text(p, path + ".value", v, MAX["value"])
        if isinstance(v, str) and re.match(r"\s*unknown\b", v, re.I):
            p.add(
                path + ".value",
                "use null for a number you couldn't read, and say why in note",
            )
    if (
        v is None
        and "value" in m
        and not (isinstance(m.get("note"), str) and m["note"].strip())
    ):
        p.add(
            path + ".note", "required when value is null: say why it couldn't be read"
        )
    if "tag" in m and m["tag"] not in TAGS:
        p.add(path + ".tag", "one of %s, or leave it out" % ", ".join(TAGS))
    _text(p, path + ".note", m.get("note"), MAX["note"])
    _as_of(p, path + ".asOf", m.get("asOf"), now)
    s = m.get("series")
    if s is not None:
        if not isinstance(s, list) or not all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
            for x in s
        ):
            p.add(path + ".series", "a list of numbers, oldest first")
        elif len(s) > MAX["series"]:
            p.add(path + ".series", "at most %d numbers" % MAX["series"])
    g = m.get("goal")
    if goal and g is not None:
        if not isinstance(g, dict):
            p.add(path + ".goal", "must be an object")
            return
        _keys(p, path + ".goal", g, ("label", "progress", "by"))
        _text(p, path + ".goal.label", g.get("label"), MAX["goal"], required=True)
        pr = g.get("progress")
        if not isinstance(pr, (int, float)) or isinstance(pr, bool) or not 0 <= pr <= 1:
            p.add(path + ".goal.progress", "a number from 0 to 1 (0.46 is 46%)")
        by = g.get("by")
        if by is not None and not (isinstance(by, str) and _DATE.match(by)):
            p.add(path + ".goal.by", "YYYY-MM-DD")


def _list(p, path, v, limit):
    if not isinstance(v, list):
        p.add(path, "must be a list")
        return []
    if len(v) > limit:
        p.add(path, "%d entries, at most %d" % (len(v), limit))
    return v


def _flag(p, path, f):
    if not isinstance(f, dict):
        p.add(path, "must be an object")
        return
    _keys(p, path, f, ("text", "tone", "detail"))
    _text(p, path + ".text", f.get("text"), MAX["flag"], required=True)
    if "tone" in f and f["tone"] not in TONES:
        p.add(path + ".tone", "one of %s" % ", ".join(TONES))
    _text(p, path + ".detail", f.get("detail"), MAX["detail"])


def _section(p, path, sec):
    if not isinstance(sec, dict):
        p.add(path, "must be an object")
        return
    _keys(p, path, sec, ("summary", "groups"))
    _text(p, path + ".summary", sec.get("summary"), MAX["summary"])
    for i, g in enumerate(
        _list(p, path + ".groups", sec.get("groups", []), MAX["groups"])
    ):
        gp = "%s.groups[%d]" % (path, i)
        if not isinstance(g, dict):
            p.add(gp, "must be an object")
            continue
        _keys(p, gp, g, ("title", "layout", "aside", "items"))
        _text(p, gp + ".title", g.get("title"), MAX["group"], required=True)
        _text(p, gp + ".aside", g.get("aside"), MAX["aside"])
        if "layout" in g and g["layout"] not in LAYOUTS:
            p.add(gp + ".layout", "row or list")
        for j, it in enumerate(
            _list(p, gp + ".items", g.get("items", []), MAX["items"])
        ):
            ip = "%s.items[%d]" % (gp, j)
            if not isinstance(it, dict):
                p.add(ip, "must be an object")
                continue
            _keys(p, ip, it, ("title", "detail", "state", "date", "url"))
            _text(p, ip + ".title", it.get("title"), MAX["item"], required=True)
            _text(p, ip + ".detail", it.get("detail"), MAX["note"])
            _text(p, ip + ".date", it.get("date"), MAX["date"])
            if "state" in it and it["state"] not in STATES:
                p.add(ip + ".state", "one of %s" % ", ".join(STATES))
            if "url" in it and not (
                isinstance(it["url"], str) and it["url"].startswith("https://")
            ):
                p.add(ip + ".url", "an https:// link")


def validate(doc, now=None):
    """Every problem with a payload (the keys a write may send), as a list of 'path: message' lines."""
    now = now or datetime.datetime.now(UTC)
    p = Problems()
    if not isinstance(doc, dict):
        p.add("snapshot", "must be a JSON object")
        return p
    legacy = {
        "asOf": "asOf goes on the headline and on each metric",
        "card": "the overview card shows the headline",
        "generatedBy": "not part of the format",
        "source": "not part of the format",
    }
    for k in sorted(set(doc) - set(ORDER)):
        p.add(
            k,
            legacy.get(
                k, "unknown key (allowed: %s)" % ", ".join(NUMBER_KEYS + KEPT_KEYS)
            ),
        )
    if doc.get("headline") is not None:
        _figure(p, "headline", doc["headline"], now, goal=True)
    if doc.get("metrics") is not None:
        for i, m in enumerate(_list(p, "metrics", doc["metrics"], MAX["metrics"])):
            _figure(p, "metrics[%d]" % i, m, now, goal=False)
    if doc.get("flags") is not None:
        for i, f in enumerate(_list(p, "flags", doc["flags"], MAX["flags"])):
            _flag(p, "flags[%d]" % i, f)
    for k in ("build", "growth"):
        if doc.get(k) is not None:
            _section(p, k, doc[k])
    if doc.get("ops") is not None:
        for i, o in enumerate(_list(p, "ops", doc["ops"], MAX["ops"])):
            if isinstance(o, str):
                _text(p, "ops[%d]" % i, o, MAX["note"])
            else:
                _flag(
                    p,
                    "ops[%d]" % i,
                    {"text": o.get("text"), "tone": o.get("tone", "info")}
                    if isinstance(o, dict)
                    else o,
                )
    if doc.get("laneRules") is not None:
        for i, r in enumerate(_list(p, "laneRules", doc["laneRules"], MAX["rules"])):
            rp = "laneRules[%d]" % i
            if not isinstance(r, dict):
                p.add(rp, "must be an object")
                continue
            _keys(p, rp, r, ("lane", "match"))
            if r.get("lane") not in LANES:
                p.add(rp + ".lane", "one of %s" % ", ".join(LANES))
            _text(p, rp + ".match", r.get("match"), MAX["match"], required=True)
            if isinstance(r.get("match"), str):
                try:
                    re.compile(r["match"])
                except re.error as e:
                    p.add(rp + ".match", "not a regular expression: %s" % e)
    s = doc.get("staleAfterDays")
    if s is not None and not (
        isinstance(s, int) and not isinstance(s, bool) and 1 <= s <= 60
    ):
        p.add("staleAfterDays", "a whole number of days from 1 to 60")
    return p


def merge(old, sent, now, by):
    """The file after a write: sent keys replace stored ones; the number keys go as one set. A file in an older
    format gives up its numbers (their shape changed) but keeps its columns and rules."""
    old = old if isinstance(old, dict) else {}
    out = {}
    numbers_from = (
        sent
        if any(k in sent for k in NUMBER_KEYS)
        else old
        if old.get("version") == VERSION
        else {}
    )
    for k in NUMBER_KEYS:
        if numbers_from.get(k) is not None:
            out[k] = numbers_from[k]
    for k in KEPT_KEYS:
        src = sent if k in sent else old
        if src.get(k) is not None:
            out[k] = src[k]
    out["version"] = VERSION
    out["updatedAt"] = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if by:
        out["updatedBy"] = by
    return {k: out[k] for k in ORDER if k in out}


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def day(v):
    try:
        t = parse_time(v)
    except (TypeError, ValueError):
        return str(v)
    if _DATE.match(v):
        return "%s %d" % (_MONTHS[t.month - 1], t.day)
    return "%s %d, %02d:%02d UTC" % (_MONTHS[t.month - 1], t.day, t.hour, t.minute)


def describe(doc):
    """What the page will show, one line per figure."""
    lines = []
    figs = ([doc["headline"]] if doc.get("headline") else []) + list(
        doc.get("metrics") or []
    )
    width = max([len(m.get("label", "")) for m in figs] + [0])
    for i, m in enumerate(figs):
        parts = [m.get("value") if m.get("value") is not None else "Unknown"]
        if m.get("tag"):
            parts[0] += " (%s)" % m["tag"]
        g = m.get("goal") if i == 0 and doc.get("headline") else None
        if g:
            parts.append(
                "%d%% of %s%s"
                % (
                    round(g["progress"] * 100),
                    g["label"],
                    ", by " + day(g["by"]) if g.get("by") else "",
                )
            )
        if m.get("note"):
            parts.append(m["note"])
        parts.append("as of " + day(m.get("asOf")))
        lines.append("  %s  %s" % (m.get("label", "").ljust(width), " · ".join(parts)))
    for f in doc.get("flags") or []:
        lines.append(
            "  flag (%s): %s%s"
            % (
                f.get("tone", "warn"),
                f.get("text"),
                " · " + f["detail"] if f.get("detail") else "",
            )
        )
    if not figs:
        lines.append("  (no numbers)")
    return "\n".join(lines)


def _git(project_dir, *args):
    return subprocess.run(
        ["git", "-C", project_dir] + list(args), capture_output=True, text=True
    )


def keep_out_of_git(project_dir):
    """Add the file to the repo's local exclude list when nothing ignores it yet. Returns a note, or None."""
    try:
        if _git(project_dir, "rev-parse", "--git-dir").returncode != 0:
            return None
        if _git(project_dir, "check-ignore", "-q", OUT_REL).returncode == 0:
            return None
        exclude = _git(
            project_dir, "rev-parse", "--git-path", "info/exclude"
        ).stdout.strip()
    except OSError:  # no git on this machine
        return None
    exclude = exclude if os.path.isabs(exclude) else os.path.join(project_dir, exclude)
    os.makedirs(os.path.dirname(exclude), exist_ok=True)
    existing = ""
    if os.path.exists(exclude):
        with open(exclude, encoding="utf-8") as f:
            existing = f.read()
    with open(exclude, "a", encoding="utf-8") as f:
        f.write(
            ("" if not existing or existing.endswith("\n") else "\n")
            + EXCLUDE_LINE
            + "\n"
        )
    return "added %s to %s, so git won't pick the file up" % (EXCLUDE_LINE, exclude)


def cmd_write(args, stdin):
    project_dir = os.path.abspath(os.path.expanduser(args.dir))
    if not os.path.isdir(project_dir):
        print("error: no folder %s" % project_dir, file=sys.stderr)
        return 2
    try:
        raw = read_json(args.file) if args.file else json.load(stdin)
    except (OSError, ValueError) as e:
        print("error: can't read the JSON you sent: %s" % e, file=sys.stderr)
        return 2
    now = datetime.datetime.now(UTC)
    problems = validate(raw, now)
    if problems:
        print(
            "refused, nothing written (%d problem%s):"
            % (len(problems), "" if len(problems) == 1 else "s"),
            file=sys.stderr,
        )
        for line in problems:
            print("  " + line, file=sys.stderr)
        return 2
    sent = {k: v for k, v in raw.items() if k not in STAMPED_KEYS}
    out = os.path.join(project_dir, OUT_REL)
    try:
        old = read_json(out)
    except (OSError, ValueError):
        old = {}
    doc = merge(old, sent, now, args.by)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, out)
    print("wrote %s" % out)
    print(describe(doc))
    note = keep_out_of_git(project_dir)
    if note:
        print(note)
    return 0


def cmd_check(args):
    project_dir = os.path.abspath(os.path.expanduser(args.dir))
    out = os.path.join(project_dir, OUT_REL)
    try:
        doc = read_json(out)
    except OSError:
        print("no snapshot at %s" % out)
        return 1
    except ValueError as e:
        print("%s is not valid JSON: %s" % (out, e))
        return 1
    if not isinstance(doc, dict) or doc.get("version") != VERSION:
        print("%s is in an older format: write it again with `snapshot.py write`" % out)
        return 1
    now = datetime.datetime.now(UTC)
    problems = validate({k: v for k, v in doc.items() if k not in STAMPED_KEYS}, now)
    print(
        "%s, updated %s%s"
        % (
            out,
            day(doc.get("updatedAt")),
            " by " + doc["updatedBy"] if doc.get("updatedBy") else "",
        )
    )
    print(describe(doc))
    for line in problems:
        print("problem: " + line)
    try:
        age = (now - parse_time(doc.get("updatedAt", ""))).total_seconds() / 86400
        limit = doc.get("staleAfterDays", 3)
        if age > limit:
            print(
                "stale: not updated for %d days (the page warns after %d)"
                % (age, limit)
            )
    except (TypeError, ValueError):
        print("problem: updatedAt is missing or unreadable")
    if (
        _git(project_dir, "rev-parse", "--git-dir").returncode == 0
        and _git(project_dir, "check-ignore", "-q", OUT_REL).returncode != 0
    ):
        print(
            "warning: git does not ignore %s; the next write adds it to the local exclude list"
            % OUT_REL
        )
    return 1 if problems else 0


def main(argv=None, stdin=None):
    ap = argparse.ArgumentParser(
        prog="snapshot.py",
        description=(__doc__ or "").split("\n\n", 1)[-1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=argparse.SUPPRESS,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="check the JSON on stdin and write it")
    w.add_argument(
        "--dir", default=".", help="the project folder (default: the current folder)"
    )
    w.add_argument("--by", help="who wrote it, shown on the page (e.g. the bot's name)")
    w.add_argument("--file", help="read the JSON from this file instead of stdin")
    c = sub.add_parser("check", help="show what the page will show, and any problem")
    c.add_argument(
        "--dir", default=".", help="the project folder (default: the current folder)"
    )
    args = ap.parse_args(argv)
    if args.cmd == "write":
        return cmd_write(args, stdin or sys.stdin)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
