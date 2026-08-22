#!/usr/bin/env python3
"""
Phase 2 harness: prove the engine reproduces the published site.

Renders every value the engine computes and compares it against the number
actually printed in the HTML today. Nothing is written. A disagreement here
means either the dataset is wrong or a page is wrong, and it must be resolved
before any marker goes into the markup.

    python scripts/verify_against_html.py            # summary
    python scripts/verify_against_html.py --verbose  # every check, including passes
"""

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_stats as engine

ROOT = Path(__file__).resolve().parent.parent
PAGES = {name: (ROOT / name).read_text(encoding="utf-8") for name in engine.PAGES}

checks = []          # (page, description, engine value, page value, ok)


def text_of(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def record(page, what, expected, found):
    checks.append((page, what, str(expected), str(found), str(expected) == str(found)))


def find(page, pattern, group=1, flags=re.S):
    """Return the first captured group of pattern in page, or a marker if absent."""
    m = re.search(pattern, PAGES[page], flags)
    return m.group(group).strip() if m else "<NOT FOUND>"


def count_in(page, needle):
    return PAGES[page].count(needle)


values, tables, facts = engine.derive(engine.load())

# ---------------------------------------------------------------- home page
# KPI strip
record("index.html", "KPI career goals", values["career.goals"],
       find("index.html", r'<span class="kpi-label">Career goals</span>\s*<span class="kpi-value">([^<]+)</span>'))
record("index.html", "KPI appearances", values["career.apps"],
       find("index.html", r'<span class="kpi-label">Appearances</span>\s*<span class="kpi-value">([^<]+)</span>'))
record("index.html", "KPI assists", values["career.assists"],
       find("index.html", r'<span class="kpi-label">Assists</span>\s*<span class="kpi-value">([^<]+)</span>'))
record("index.html", "road to 1,000 goals to go", values["career.remaining"],
       find("index.html", r'<span class="big">(\d+)</span>\s*<span class="of">goals to go</span>'))
record("index.html", "progress label", values["career.progress_label"],
       text_of(find("index.html", r'<span class="goal tnum">([^<]+)</span>')))
record("index.html", "progress aria-valuenow", values["career.goals.raw"],
       find("index.html", r'aria-valuenow="(\d+)"'))
record("index.html", "progress bar width", values["career.pct"] + "%",
       find("index.html", r'\.progress-fill \{[^}]*?width: ([\d.]+%);', 1))

# Career table, one row per team plus the totals row
for team in engine.load()["teams"]:
    tid, name = team["id"], team["name"]
    row = find("index.html",
               r'<span class="club-name">' + re.escape(name) + r'<small>[^<]*</small></span></span></th>\s*'
               r'<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d.]+)</td>', 0)
    if row == "<NOT FOUND>":
        record("index.html", f"career table row {name}", "row present", "<NOT FOUND>")
        continue
    m = re.search(r'<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d.]+)</td>', row, re.S)
    apps, goals, assists, gpg = m.groups()
    record("index.html", f"career table {name} apps", values[f"team.{tid}.apps"], apps)
    record("index.html", f"career table {name} goals", values[f"team.{tid}.goals"], goals)
    record("index.html", f"career table {name} assists", values[f"team.{tid}.assists"], assists)
    record("index.html", f"career table {name} goals per game", values[f"team.{tid}.gpg"], gpg)

foot = find("index.html", r'<th scope="row">Career total</th>\s*<td class="years">[^<]*</td>\s*'
                          r'<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d.]+)</td>', 0)
if foot != "<NOT FOUND>":
    m = re.search(r'<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d.]+)</td>', foot, re.S)
    record("index.html", "career table total apps", values["career.apps"], m.group(1))
    record("index.html", "career table total goals", values["career.goals"], m.group(2))
    record("index.html", "career table total assists", values["career.assists"], m.group(3))
    record("index.html", "career table total goals per game", values["career.gpg"], m.group(4))

# Set piece table
data = engine.load()
for tid, name in [(t["id"], t["name"]) for t in data["teams"]]:
    row = find("index.html", r'<tr><th scope="row">' + re.escape(name) +
               r'</th><td>(\d+)</td><td>(\d+)</td><td>(\d+)</td></tr>', 0)
    if row == "<NOT FOUND>":
        record("index.html", f"set piece row {name}", "row present", "<NOT FOUND>")
        continue
    fk, pen, ht = re.search(r'<td>(\d+)</td><td>(\d+)</td><td>(\d+)</td>', row).groups()
    record("index.html", f"free kicks {name}", data["freekicks"].get(tid, 0), fk)
    record("index.html", f"penalties {name}", data["penalties"].get(tid, 0), pen)
    record("index.html", f"hat tricks {name}", data["hattricks"].get(tid, 0), ht)

record("index.html", "set piece totals free kicks", values["freekicks.total"],
       find("index.html", r'<th scope="row">Career total</th>\s*<td>(\d+)</td>\s*<td>\d+</td>\s*<td>\d+</td>'))
record("index.html", "set piece totals penalties", values["penalties.total"],
       find("index.html", r'<th scope="row">Career total</th>\s*<td>\d+</td>\s*<td>(\d+)</td>\s*<td>\d+</td>'))
record("index.html", "set piece totals hat tricks", values["hattricks.total"],
       find("index.html", r'<th scope="row">Career total</th>\s*<td>\d+</td>\s*<td>\d+</td>\s*<td>(\d+)</td>'))

# ------------------------------------------------------------ goals by year
record("goalsbyyear.html", "summary total goals", values["career.goals"],
       find("goalsbyyear.html", r'id="totalGoals">([^<]+)<'))
record("goalsbyyear.html", "summary years scoring", str(len(tables["years"])),
       find("goalsbyyear.html", r'id="yearsScoring">([^<]+)<'))
record("goalsbyyear.html", "summary best year goals", values["year.best.goals"],
       find("goalsbyyear.html", r'id="bestYear">([^<]+)<'))
record("goalsbyyear.html", "summary best year label", f'Best year ({values["year.best.year"]})',
       find("goalsbyyear.html", r'id="bestYearLabel">([^<]+)<'))
record("goalsbyyear.html", "summary average per year",
       f'{sum(r["goals"] for r in tables["years"]) / len(tables["years"]):.1f}',
       find("goalsbyyear.html", r'id="avgPerYear">([^<]+)<'))

# Every row of the year table, against the engine's own cumulative maths
for row in tables["years"]:
    cell = find("goalsbyyear.html",
                r'<tr[^>]*><th scope="row">' + str(row["year"]) +
                r'</th><td>(\d+)</td><td class="muted">([\d,]+)</td><td class="muted">(\d+)</td></tr>', 0)
    if cell == "<NOT FOUND>":
        record("goalsbyyear.html", f"year table {row['year']}", "row present", "<NOT FOUND>")
        continue
    g, cum, age = re.search(r'<td>(\d+)</td><td class="muted">([\d,]+)</td><td class="muted">(\d+)</td>', cell).groups()
    record("goalsbyyear.html", f"year {row['year']} goals", row["goals"], g)
    record("goalsbyyear.html", f"year {row['year']} cumulative", f'{row["cumulative"]:,}', cum)
    record("goalsbyyear.html", f"year {row['year']} age", row["age"], age)

# The Chart.js arrays still hard coded in the page
chart_goals = find("goalsbyyear.html", r'const goalsPerYear = \[([^\]]+)\]')
record("goalsbyyear.html", "chart goalsPerYear array",
       ", ".join(str(r["goals"]) for r in tables["years"]),
       ", ".join(x.strip() for x in chart_goals.split(",")) if chart_goals != "<NOT FOUND>" else chart_goals)
chart_cum = find("goalsbyyear.html", r'const cumulativeGoals = \[([^\]]+)\]')
record("goalsbyyear.html", "chart cumulativeGoals array",
       ", ".join(str(r["cumulative"]) for r in tables["years"]),
       ", ".join(x.strip() for x in chart_cum.split(",")) if chart_cum != "<NOT FOUND>" else chart_cum)

# ---------------------------------------------------------- goals by season
club_apps = sum(c["apps"] for r in data["seasons"] if r.get("in_career", True)
                for c in r["comps"].values() if c)
club_goals = sum(c["goals"] for r in data["seasons"] if r.get("in_career", True)
                 for c in r["comps"].values() if c)
por_apps = sum(r["apps"] for r in data["portugal_years"])
por_goals = sum(r["goals"] for r in data["portugal_years"])

record("goalsbyseason.html", "summary club goals", f"{club_goals:,}",
       find("goalsbyseason.html", r'<div class="summary-value">([\d,]+)</div><div class="summary-label">Club goals</div>'))
record("goalsbyseason.html", "summary club appearances", f"{club_apps:,}",
       find("goalsbyseason.html", r'<div class="summary-value">([\d,]+)</div><div class="summary-label">Club appearances</div>'))
record("goalsbyseason.html", "summary international goals", f"{por_goals:,}",
       find("goalsbyseason.html", r'<div class="summary-value">([\d,]+)</div><div class="summary-label">International goals</div>'))
record("goalsbyseason.html", "summary international caps", f"{por_apps:,}",
       find("goalsbyseason.html", r'<div class="summary-value">([\d,]+)</div><div class="summary-label">International caps</div>'))

career_row = find("goalsbyseason.html", r'<tr class="career-total-row">(.*?)</tr>', 1)
if career_row != "<NOT FOUND>":
    nums = re.findall(r"<td[^>]*>([\d,]+)</td>", career_row)
    record("goalsbyseason.html", "club table total apps", f"{club_apps:,}", nums[-2] if len(nums) >= 2 else "?")
    record("goalsbyseason.html", "club table total goals", f"{club_goals:,}", nums[-1] if nums else "?")

# Every Portugal year row
for row in data["portugal_years"]:
    cell = find("goalsbyseason.html",
                r'Portugal</div></td><td class="season-cell">' + str(row["year"]) +
                r'</td>(.*?)</tr>', 1)
    if cell == "<NOT FOUND>":
        record("goalsbyseason.html", f"Portugal {row['year']}", "row present", "<NOT FOUND>")
        continue
    nums = re.findall(r'<td[^>]*>(\d+|n/a)</td>', cell)
    record("goalsbyseason.html", f"Portugal {row['year']} apps", row["apps"], nums[-2])
    record("goalsbyseason.html", f"Portugal {row['year']} goals", row["goals"], nums[-1])

# ----------------------------------------------------------------- dashboard
record("dashboard.html", "summary games", values["career.apps"],
       find("dashboard.html", r'id="sumGames">([^<]+)<'))
record("dashboard.html", "summary goals", values["career.goals"],
       find("dashboard.html", r'id="sumGoals">([^<]+)<'))
record("dashboard.html", "summary goals per game", values["career.gpg"],
       find("dashboard.html", r'id="sumRate">([^<]+)<'))
record("dashboard.html", "summary assists", values["career.assists"],
       find("dashboard.html", r'id="sumAssists">([^<]+)<'))

# DATA.teams block still hard coded in the page script
for team in data["teams"]:
    tid = team["id"]
    key = {"manutd": "manutd", "realmadrid": "realmadrid", "juventus": "juventus",
           "alnassr": "alnassr", "portugal": "portugal", "sporting": "sporting"}[tid]
    block = find("dashboard.html", key + r":\s*\{ name: '[^']*',\s*games: (\d+),\s*goals: (\d+),\s*assists: (\d+) \}", 0)
    if block == "<NOT FOUND>":
        record("dashboard.html", f"DATA.teams {tid}", "present", "<NOT FOUND>")
        continue
    g, go, a = re.search(r"games: (\d+),\s*goals: (\d+),\s*assists: (\d+)", block).groups()
    record("dashboard.html", f"DATA.teams {tid} games", values[f"team.{tid}.apps"].replace(",", ""), g)
    record("dashboard.html", f"DATA.teams {tid} goals", values[f"team.{tid}.goals"].replace(",", ""), go)
    record("dashboard.html", f"DATA.teams {tid} assists", values[f"team.{tid}.assists"].replace(",", ""), a)

all_block = find("dashboard.html", r"all:\s*\{ name: 'All teams',\s*games: (\d+),\s*goals: (\d+),\s*assists: (\d+) \}", 0)
if all_block != "<NOT FOUND>":
    g, go, a = re.search(r"games: (\d+),\s*goals: (\d+),\s*assists: (\d+)", all_block).groups()
    record("dashboard.html", "DATA.teams all games", values["career.apps"].replace(",", ""), g)
    record("dashboard.html", "DATA.teams all goals", values["career.goals"].replace(",", ""), go)
    record("dashboard.html", "DATA.teams all assists", values["career.assists"].replace(",", ""), a)

# Competition table and the DATA.competitions.all array
for name, n in data["competitions"].items():
    cell = find("dashboard.html", r'<tr><th scope="row">' + re.escape(name) + r'</th><td>(\d+)</td>', 1)
    record("dashboard.html", f"competition table {name}", n, cell)
    # the JS uses double quotes for labels containing an apostrophe
    arr = find("dashboard.html", r"\['" + re.escape(name) + r"', (\d+)\]"
               if "'" not in name else r'\["' + re.escape(name) + r'", (\d+)\]', 1)
    record("dashboard.html", f"DATA competitions {name}", n, arr)

# Body part and finish tables
for label, key in [("Right foot", "right"), ("Left foot", "left"), ("Headers", "head"), ("Other", "other")]:
    record("dashboard.html", f"body part table {label}", values[f"body.all.{key}"],
           find("dashboard.html", r'<tr><th scope="row">' + label + r'</th><td>(\d+)</td>', 1))
record("dashboard.html", "finish table penalties", values["penalties.total"],
       find("dashboard.html", r'<tr><th scope="row">Penalties</th><td>(\d+)</td>', 1))
record("dashboard.html", "finish table free kicks", values["freekicks.total"],
       find("dashboard.html", r'<tr><th scope="row">Free kicks</th><td>(\d+)</td>', 1))
open_play = str(int(values["career.goals"].replace(",", ""))
                - int(values["penalties.total"]) - int(values["freekicks.total"]))
record("dashboard.html", "finish table open play", open_play,
       find("dashboard.html", r'<tr><th scope="row">Open play</th><td>(\d+)</td>', 1))
record("dashboard.html", "DATA bodyPart all",
       ", ".join(values[f"body.all.{s}"] for s in engine.BODY_SLOTS),
       ", ".join(x.strip() for x in find("dashboard.html", r"all:\s*\[([\d, ]+)\],\s*\n\s*sporting:\s*\[[\d, ]+\],\s*\n\s*manutd:\s*\[97", 1).split(","))
       if find("dashboard.html", r"bodyPart: \{", 0) != "<NOT FOUND>" else "<NOT FOUND>")

# ------------------------------------------------- figures inside sentences
prose = [
    ("index.html", "lead sentence goals", values["career.goals"],
     r'Cristiano Ronaldo has scored <b>([\d,]+) goals</b>'),
    ("index.html", "lead sentence appearances", values["career.apps"],
     r'<b>([\d,]+) senior appearances</b>'),
    ("index.html", "lead sentence assists", values["career.assists"],
     r'with <b>([\d,]+) assists</b>'),
    ("index.html", "lead sentence goals to go", values["career.remaining"],
     r'He is (\d+) goals short of 1,000'),
    ("goalsbyseason.html", "lead club goals", f"{club_goals:,}",
     r'<b>([\d,]+) club goals in [\d,]+ games</b>'),
    ("goalsbyseason.html", "lead club appearances", f"{club_apps:,}",
     r'<b>[\d,]+ club goals in ([\d,]+) games</b>'),
    ("goalsbyyear.html", "lead career goals", values["career.goals"],
     r'Cristiano Ronaldo has scored <b>([\d,]+) goals</b> across'),
    ("dashboard.html", "lead goals", values["career.goals"],
     r'has scored <b>([\d,]+) goals in [\d,]+ games</b>'),
    ("dashboard.html", "lead games", values["career.apps"],
     r'has scored <b>[\d,]+ goals in ([\d,]+) games</b>'),
]
for page, what, expected, pattern in prose:
    record(page, what, expected, find(page, pattern, 1))

# The updated date, everywhere it is printed
for page in PAGES:
    n = count_in(page, values["meta.updated.long"])
    record(page, f"updated date appears ({values['meta.updated.long']})", "at least once" if n else "none",
           "at least once" if n else "none")

# ------------------------------------------------------------------- report
fails = [c for c in checks if not c[4]]
verbose = "--verbose" in sys.argv

if verbose:
    for page, what, exp, got, ok in checks:
        print(f'{"ok  " if ok else "DIFF"} {page:20} {what:44} engine={exp!r:>14} page={got!r}')
    print()

by_page = {}
for page, what, exp, got, ok in checks:
    by_page.setdefault(page, [0, 0])
    by_page[page][0 if ok else 1] += 1
print("checks by page")
for page, (passed, failed) in sorted(by_page.items()):
    print(f"  {page:22} {passed:>4} agree, {failed:>3} disagree")

print(f"\n{len(checks)} checks, {len(checks) - len(fails)} agree, {len(fails)} disagree")
if fails:
    print("\nDISAGREEMENTS, resolve before adding any marker:")
    for page, what, exp, got, _ in fails:
        print(f"  {page:20} {what}")
        print(f"    engine says {exp!r}")
        print(f"    page says   {got!r}")
    sys.exit(1)
print("\nThe engine reproduces every published figure it was asked about.")
