#!/usr/bin/env python3
"""
Phase 4 gate: no published statistic may be hand maintained.

Every figure the site prints must be reachable by the engine, either through a
data-stat marker, a STATS region, or a head text rule. This walks each page and
reports any number that is none of those and that also matches a value the
engine computes, which is the definition of a figure that will go stale.

    python scripts/check_coverage.py            # summary
    python scripts/check_coverage.py --list     # every uncovered number

Numbers that are not statistics, such as dates in the career history, fees,
ages at a moment in time and award years, are listed in ALLOWED below with the
reason they are exempt. Exit code 1 if anything is uncovered and unexplained.
"""

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_stats as engine

ROOT = Path(__file__).resolve().parent.parent
LIST = "--list" in sys.argv

# Figures the pages print that are deliberately not driven by the dataset. Each
# is a pattern matched against the surrounding text, with the reason it is
# exempt. Anything here is a decision on the record, not an oversight.
EXEMPT = {
    "timeline.html": [
        (r"debut at 17|At 17 he broke", "his age at the time, fixed by the event"),
        (r"aged 19|At 19 he scored", "his age at the time, fixed by the event"),
        (r"Ballon d'Or at 23", "his age at the time, fixed by the event"),
        (r"a Serie A record at 33|At 33 he became", "his age at the time, fixed by the event"),
        (r"24 year career", "the length of the career so far, written as prose"),
        (r"£12\.24m|€94m|€117m|€100m", "transfer fees, fixed by the event"),
        (r"in a 42 goal season|crowning a 42 goal season",
         "the 2007/08 total, quoted as history rather than as a live figure"),
        (r"La Liga with 46 league goals|121 goals, 46 of them his",
         "the 2011/12 league total and Real Madrid's team total that season"),
        (r"a record 17 goals in the campaign|His 17 goals that season",
         "the 2013/14 Champions League record, a competition record not a career one"),
        (r"100 points", "Real Madrid's points total in 2011/12, not a Ronaldo figure"),
        (r"all 96 ballots", "the Ballon d'Or vote in 2008"),
        (r"Ballon d'Or at 23", "his age at the time, fixed by the event"),
        (r"Serie A's record signing at 33", "his age at the time, fixed by the event"),
        (r"take him to a record 14 at the Euros",
         "his Euros total at the end of Euro 2020, quoted as history"),
        (r"Injured after 25 minutes", "minutes played in the Euro 2016 final"),
        (r"United pay £12\.24m|rising to 117 million|rising to €117m",
         "transfer fees, fixed by the event"),
        (r"100 points and 121 goals, 46 of them",
         "the 2011/12 league total and Real Madrid's team total that season"),
        (r"On 23 June 2026|23 June 2026 a brace", "the date of the sixth World Cup"),
        (r"final after 25 minutes", "minutes played in the Euro 2016 final"),
        (r"took him to 14 at European Championships",
         "his Euros total at the end of Euro 2020, quoted as history"),
    ],
    "goalsbyseason.html": [
        (r"Portugal U15|Portugal U17|Portugal U20|Portugal U21",
         "youth international football, excluded from every career total by design"),
        (r"International career total",
         "this row adds the youth caps to the senior ones, so it is deliberately "
         "outside the career dataset"),
    ],
    "achievements.html": [
        (r"FIFA FIFPro World 11", "the 11 is part of the award's name, not a count"),
    ],
}


def visible(text):
    """The page as a reader meets it: no scripts, no styles, no head."""
    text = text[text.index("<body"):]
    text = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", text, flags=re.S)
    return text


def covered_spans(text):
    """Character ranges already driven by the engine."""
    spans = []
    for m in re.finditer(r'<(\w+)\b[^>]*\sdata-stat(?:-attr)?="[^"]*"[^>]*>(.*?)</\1>',
                         text, re.S):
        spans.append((m.start(2), m.end(2)))
    for m in engine.REGION_RE.finditer(text):
        spans.append((m.start("body"), m.end("body")))
    return spans


def rule_spans(text, page):
    """Figures driven by a script rule are covered too, even though they carry
    no marker: the build rewrites them and reports if a pattern stops matching."""
    spans = []
    for rule in engine.script_rules().get(page, []):
        for m in re.finditer(rule[0], text):
            spans.append((m.start(1), m.end(1)))
    return spans


def head_gaps(text, page, values, engine_values):
    """The same question for the head: is every figure in a title, a meta
    description or a JSON-LD string driven by a text rule? Only the parts a
    search engine reads are scanned, never the stylesheet."""
    head = text.split("</head>")[0]
    spans = []
    for rule in engine.text_rules().get(page, []):
        for m in re.finditer(rule[0], head):
            spans.append((m.start(1), m.end(1)))
    chars = list(head)
    for a, b in spans:
        for i in range(a, b):
            chars[i] = " "
    head = "".join(chars)

    # only the machine readable text, not the CSS
    pieces = re.findall(r'<title>(.*?)</title>', head, re.S)
    pieces += re.findall(r'<meta (?:name|property)="[^"]*(?:title|description)" content="([^"]*)"', head)
    pieces += [m for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', head, re.S)]

    gaps = []
    for piece in pieces:
        piece = re.sub(r"\b(19|20)\d\d/\d\d\b", " ", piece)
        piece = re.sub(r"\b\d{1,2} (?:January|February|March|April|May|June|July|August|"
                       r"September|October|November|December) \d{4}\b", " ", piece)
        piece = re.sub(r'"(?:startDate|dateModified|datePublished)": "[^"]*"', " ", piece)
        for m in re.finditer(r"(?<![\w.\-])(\d[\d,]*(?:\.\d+)?)(?![\w])", piece):
            n = m.group(1)
            if n not in engine_values or re.fullmatch(r"(19|20)\d\d", n) or re.fullmatch(r"\d", n):
                continue
            ctx = re.sub(r"\s+", " ", piece[max(0, m.start() - 60):m.end() + 30]).strip()
            gaps.append((n, "head: " + ctx))
    return gaps


def main():
    values, _, _ = engine.derive(engine.load())
    # the set of figures the engine can produce, as printed
    engine_values = {v for v in values.values() if re.fullmatch(r"[\d,]+(?:\.\d+)?", str(v))}

    total_uncovered = 0
    per_page = {}
    exempt = {}
    for name in engine.PAGES:
        text = (ROOT / name).read_text(encoding="utf-8")
        body = visible(text)
        spans = covered_spans(body) + rule_spans(body, name)

        def inside(pos):
            return any(a <= pos < b for a, b in spans)

        # blank out covered ranges, then read what is left as a reader would
        chars = list(body)
        for a, b in spans:
            for i in range(a, b):
                chars[i] = " "
        left = re.sub(r"<[^>]+>", " ", "".join(chars))
        left = html.unescape(left)
        # Drop the things that look like figures but are not: season labels,
        # full dates, short season pairs and day-of-month in a date range.
        left = re.sub(r"\b(19|20)\d\d/\d\d\b", " ", left)          # 2014/15
        left = re.sub(r"\b\d\d/\d\d\b", " ", left)                  # 14/15
        left = re.sub(r"\b\d{1,2} (January|February|March|April|May|June|July|"
                      r"August|September|October|November|December)\b", " ", left)
        left = re.sub(r"\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
                      " ", left)

        hits = []
        for m in re.finditer(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?![\w])", left):
            n = m.group(1)
            if n not in engine_values:
                continue                      # not a figure the engine can produce
            if re.fullmatch(r"(19|20)\d\d", n):
                continue                      # a year in the career history
            if re.fullmatch(r"\d", n):
                # a single digit matches some engine value by chance far too
                # often, and every published statistic worth guarding is bigger
                continue
            ctx = re.sub(r"\s+", " ", left[max(0, m.start() - 60):m.end() + 40]).strip()
            reason = next((why for pat, why in EXEMPT.get(name, [])
                           if re.search(pat, ctx)), None)
            if reason:
                exempt.setdefault(reason, 0)
                exempt[reason] += 1
                continue
            hits.append((n, ctx))
        # The updated date is a published figure too, and it is easy to miss
        # because it is not a number the scan would pick up.
        for m in re.finditer(re.escape(values["meta.updated.long"]), body):
            if not any(a <= m.start() < b for a, b in spans):
                ctx = re.sub(r"\s+", " ", body[max(0, m.start() - 70):m.end()])
                ctx = re.sub(r"<[^>]+>", "", ctx).strip()
                hits.append((values["meta.updated.long"], "updated date: " + ctx))

        for n, ctx in head_gaps(text, name, values, engine_values):
            reason = next((why for pat, why in EXEMPT.get(name, []) if re.search(pat, ctx)), None)
            if reason:
                exempt[reason] = exempt.get(reason, 0) + 1
            else:
                hits.append((n, ctx))
        per_page[name] = hits
        total_uncovered += len(hits)

    print("uncovered figures that the engine could otherwise drive")
    for name, hits in per_page.items():
        print(f"  {name:22} {len(hits):>3}")
        if LIST:
            for n, ctx in hits:
                print(f"      {n:>7}  {ctx}")
    if exempt:
        print("\nexempt, with the reason on the record")
        for reason, n in sorted(exempt.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>3}  {reason}")
    print(f"\n{total_uncovered} uncovered")
    if not LIST and total_uncovered:
        print("run with --list to see them")
    return 1 if total_uncovered else 0


if __name__ == "__main__":
    sys.exit(main())
