#!/usr/bin/env python3
"""
Generate scripts/head_rules.py from the pages as they stand today.

The titles, meta descriptions and JSON-LD blocks repeat the site's figures in
running prose, and there are far too many to hand write a pattern for each. So
they are generated: every figure in the head that matches a value the engine
computes gets a rule anchored on the words around it.

    python scripts/gen_head_rules.py            # rewrite scripts/head_rules.py
    python scripts/gen_head_rules.py --dry-run  # show what it would write

Run this only when the head prose changes. It reads the current pages, so it can
only be trusted when those pages agree with the dataset: it refuses to run if
scripts/verify_against_html.py would disagree, and every rule it writes is
checked on every build, so a stale rule is reported rather than ignored.

Ambiguity is resolved by widening the anchor until the pattern matches exactly
once, and a figure whose value could belong to more than one key is skipped and
listed, because guessing there would publish the wrong number later.
"""

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_stats as engine

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scripts" / "head_rules.py"
DRY = "--dry-run" in sys.argv
COMP_LABELS = []

# Keys that are the natural home for a figure when several share a value. The
# first match wins, so the more specific keys come first.
PREFERENCE = [
    "career.goals", "career.apps", "career.assists", "career.gpg", "career.target",
    "career.remaining", "career.club_goals", "career.club_apps",
    "season.current.goals", "season.current.league_goals",
    "year.current.goals", "year.best.goals", "season.best.goals", "season.best.apps",
    "honours.total", "honours.club", "honours.national", "honours.leagues",
    "honours.championsleague", "award.ballondor", "award.floor",
    "penalties.total", "freekicks.total", "hattricks.total",
    "career.penalty_pct", "career.openplay", "career.assist_rate",
]

# Key families that only ever duplicate a value another key owns: positional
# season and spell rows, per team aggregates, opponent and body part tallies.
# A figure in running prose never means one of these.
SKIP_KEY = re.compile(r"^(season\.\d+\.|portugal\.\d{4}\.|milestone\.|opponent\.|"
                      r"body\.|openplay\.|spell\.|club\.total\.|year\.rank|"
                      r"season\.rank|comp\.\w+\.total$|team\.\w+\.bestseason)")

TEAM_WORDS = {"Real Madrid": "realmadrid", "Manchester United": "manutd",
              "Man United": "manutd", "Portugal": "portugal", "Al Nassr": "alnassr",
              "Juventus": "juventus", "Sporting CP": "sporting"}
NOUNS = [("goals", "goals"), ("appearances", "apps"), ("games", "apps"),
         ("caps", "apps"), ("assists", "assists")]

# Words that name an award or a set piece, so a bare figure beside one of them
# is that thing's count rather than a coincidence.
NAMED = [("Ballon d'Or", "award.ballondor"),
         ("The Best FIFA", "award.thebestfifamensplayer"),
         ("European Golden Shoe", "award.europeangoldenshoe"),
         ("FIFPro World 11", "award.fifafifproworld11"),
         ("hat trick", "hattricks.total"), ("hat-trick", "hattricks.total"),
         ("free kick", "freekicks.total"), ("penalt", "penalties.total"),
         ("team trophies", "honours.total"), ("league titles", "honours.leagues")]


def head_of(page):
    return (ROOT / page).read_text(encoding="utf-8").split("</head>")[0]


def machine_text(head):
    """The ranges of the head a search engine actually reads."""
    spans = []
    for m in re.finditer(r"<title>(.*?)</title>", head, re.S):
        spans.append((m.start(1), m.end(1)))
    for m in re.finditer(r'<meta (?:name|property)="[^"]*(?:title|description)" '
                         r'content="([^"]*)"', head):
        spans.append((m.start(1), m.end(1)))
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>',
                         head, re.S):
        spans.append((m.start(1), m.end(1)))
    return spans


def choose_key(value, candidates, before, after):
    """Pick the key this figure means. Context first, since "Real Madrid: 450
    goals" is unambiguous even though 450 matches several keys, then the general
    preference order, and only then a lone survivor."""
    noun = next((slot for word, slot in NOUNS
                 if re.match(r"[^a-zA-Z]{0,3}" + word + r"\b", after)), None)
    if noun:
        # the nearest team name before the figure, if there is one
        hits = [(before.rfind(word), tid) for word, tid in TEAM_WORDS.items()
                if word in before]
        if hits:
            _, tid = max(hits)
            want = f"team.{tid}.{noun}"
            if want in candidates:
                return want
        for want in (f"career.{noun}", f"career.{'club_' + noun}"):
            if want in candidates:
                return want
    # a year named right before the figure: "2013: 69 goals"
    my = re.search(r"\b((?:19|20)\d\d)[^a-zA-Z0-9]{0,4}$", before)
    if my and noun in ("goals", None):
        want = f"year.{my.group(1)}.goals"
        if want in candidates:
            return want
    # a per team set piece tally inside a sentence about the whole career:
    # "66 free kick goals: 33 for Real Madrid, 15 for Manchester United"
    sentence = before[-200:] + after[:40]
    group = next((g for word, g in (("free kick", "freekicks"), ("penalt", "penalties"),
                                    ("hat trick", "hattricks")) if word in sentence.lower()), None)
    if group:
        run = before[-40:] + after[:30]
        hits = [(run.find(word), tid) for word, tid in TEAM_WORDS.items() if word in run]
        if hits:
            _, tid = min(hits)
            want = f"{group}.{tid}"
            if want in candidates:
                return want
    # "2014/15 at Real Madrid: 61 goals"
    ms = re.search(r"\b((?:19|20)\d\d/\d\d)\b(.{0,30})$", before, re.S)
    if ms and noun in ("goals", "apps", None):
        tid = next((t for w, t in TEAM_WORDS.items() if w in ms.group(2)), None)
        if tid:
            want = f"season.{ms.group(1).replace('/', '-')}.{tid}.{noun or 'goals'}"
            if want in candidates:
                return want
    # a team and a competition together: "21 for Manchester United" inside a
    # Champions League sentence means that club's tally in that competition
    near = before[-45:] + after[:40]
    for label in COMP_LABELS:
        if label.lower() not in near.lower():
            continue
        for word, tid in TEAM_WORDS.items():
            if word in near:
                want = f"comp.{tid}.{engine.slug(label)}"
                if want in candidates:
                    return want
    # a competition named right after the figure: "140 Champions League goals"
    tail = re.sub(r"^[^a-zA-Z]{0,3}", "", after)
    for label in COMP_LABELS:
        if tail.lower().startswith(label.lower()):
            want = f"comp.{engine.slug(label)}"
            if want in candidates:
                return want
    # or named right before it: "Saudi Pro League: 102 goals"
    for label in COMP_LABELS:
        if re.search(re.escape(label) + r"[^a-zA-Z]{0,4}$", before):
            want = f"comp.{engine.slug(label)}"
            if want in candidates:
                return want
    for word, want in NAMED:
        if word.lower() in (before[-70:] + tail[:40]).lower() and want in candidates:
            return want
    for want in PREFERENCE:
        if want in candidates:
            return want
    plain = [k for k in candidates if not SKIP_KEY.match(k)]
    return sorted(plain)[0] if len(plain) == 1 else None


DATE_RE = re.compile(r"\d{1,2} (?:January|February|March|April|May|June|July|August|"
                     r"September|October|November|December) \d{4}|\d{4}-\d\d-\d\d")


def anchor_for(head, pos, end, width):
    """A pattern that pins this figure using the words around it. Digits in the
    context are replaced by a class, so a rule does not break when a neighbouring
    figure moves."""
    before = head[max(0, pos - width):pos]
    after = head[end:end + max(8, width // 3)]
    # a date in the anchor moves every time the site is updated, which would
    # break the rule on the very build that needed it
    before = DATE_RE.sub("@", before)
    after = DATE_RE.sub("@", after)
    def lit(s):
        # a four digit year in the context is stable and is often the only thing
        # telling two list entries apart, so keep those literal and loosen the
        # rest, which may move when a figure changes
        out, i = [], 0
        for m in re.finditer(r"(?:19|20)\d\d", s):
            out.append(re.sub(r"[\d,]+", r"[\\d,]+", re.escape(s[i:m.start()])))
            out.append(re.escape(m.group(0)))
            i = m.end()
        out.append(re.sub(r"[\d,]+", r"[\\d,]+", re.escape(s[i:])))
        return "".join(out).replace("@", r"[\w ]+")
    return lit(before) + r"([\d,]+(?:\.\d+)?)" + lit(after)


def main():
    global COMP_LABELS
    values, _, _ = engine.derive(engine.load())
    # longest first, so "Champions League" never wins over "AFC Champions League"
    COMP_LABELS = sorted(engine.career_competitions(engine.load()), key=len, reverse=True)
    by_value = {}
    for k, v in values.items():
        by_value.setdefault(str(v), []).append(k)

    rules, skipped = {}, []
    for page in engine.PAGES:
        head = head_of(page)
        covered = []
        for rule in engine.text_rules(generated=False).get(page, []):
            for m in re.finditer(rule[0], head):
                covered.append((m.start(1), m.end(1)))

        page_rules, seen = [], set()
        for lo, hi in machine_text(head):
            piece = head[lo:hi]
            for m in re.finditer(r"(?<![\w.\-])(\d[\d,]*(?:\.\d+)?)(?![\w])", piece):
                pos, end = lo + m.start(1), lo + m.end(1)
                n = m.group(1)
                if any(a <= pos < b for a, b in covered):
                    continue
                if re.fullmatch(r"(19|20)\d\d", n) or re.fullmatch(r"\d", n):
                    continue
                if re.search(r"(?:19|20)\d\d/$", head[:pos]):
                    continue                      # the "15" of a 2014/15 label
                if n not in by_value:
                    continue
                # never rewrite a schema.org position or a date
                lead = head[max(0, pos - 40):pos]
                if re.search(r'"(?:position|numberOfItems)":\s*$', lead):
                    continue
                if re.search(r'"(?:startDate|endDate|dateModified|datePublished)": "[^"]*$', lead):
                    continue
                key = choose_key(n, by_value[n], head[max(0, pos - 120):pos],
                                 head[end:end + 24])
                if key is None:
                    skipped.append((page, n, sorted(by_value[n])[:4]))
                    continue
                for width in (24, 40, 60, 90):
                    pat = anchor_for(head, pos, end, width)
                    if len(re.findall(pat, head)) == 1:
                        break
                else:
                    skipped.append((page, n, ["ambiguous even at width 90"]))
                    continue
                if pat in seen:
                    continue
                # the rule must read back the value the engine already holds,
                # or it would rewrite this figure into the wrong number
                found = re.search(pat, head)
                if not found or found.group(1) != str(values[key]):
                    skipped.append((page, n, [f"{key} reads back "
                                              f"{found.group(1) if found else 'nothing'}"]))
                    continue
                seen.add(pat)
                page_rules.append((pat, key))
        if page_rules:
            rules[page] = page_rules

    total = sum(len(v) for v in rules.values())
    print(f"{total} generated rules across {len(rules)} pages")
    for page, v in rules.items():
        print(f"  {page:22} {len(v):>3}")
    if skipped:
        print(f"\n{len(skipped)} figures skipped, listed so they are not forgotten:")
        for page, n, why in skipped[:20]:
            print(f"  {page:22} {n:>7}  {why}")

    body = ['"""',
            "Generated by scripts/gen_head_rules.py. Do not edit by hand.",
            "",
            "One rule per figure printed in a title, a meta description or a JSON-LD",
            "block. Each is a pattern with a single capturing group and the key that",
            "fills it. Every rule is checked on each build: one that stops matching, or",
            "matches more than once, is reported rather than silently skipped.",
            "",
            "Regenerate after editing the head prose of any page.",
            '"""',
            "",
            "RULES = {"]
    for page, v in rules.items():
        body.append(f"    {page!r}: [")
        for pat, key in v:
            body.append(f"        ({pat!r}, {key!r}),")
        body.append("    ],")
    body.append("}")
    text = "\n".join(body) + "\n"
    if DRY:
        print("\n(dry run, nothing written)")
    else:
        OUT.write_text(text, encoding="utf-8")
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
