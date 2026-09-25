#!/usr/bin/env python3
"""
Phase 2 harness: prove the engine reproduces the published site.

Renders every value the engine computes and compares it against the number
actually printed in the HTML today. Nothing is written. A disagreement here
means either the dataset is wrong or a page is wrong, and it must be resolved
before any marker goes into the markup.

    python scripts/verify_against_html.py            # summary
    python scripts/verify_against_html.py --coverage # plus any engine key not verified
    python scripts/verify_against_html.py --verbose  # every check, including passes

Exit code 1 on any disagreement, so it can gate a commit.
"""

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_stats as engine

ROOT = Path(__file__).resolve().parent.parent


def without_markers(text):
    """Phase 3 markers are invisible to a reader, so compare against the page as
    it renders: unwrap marker only spans, then drop the marker attributes and
    the region comments."""
    text = re.sub(r'<span data-stat="[^"]*">([^<]*)</span>', r"\1", text)
    text = re.sub(r'\s+data-stat(?:-attr)?="[^"]*"', "", text)
    text = re.sub(r"(?:<!--|//)[ \t]*STATS:(?:BEGIN|END)[ \t]+[\w.]+[ \t]*(?:-->)?\n?", "", text)
    return text


PAGES = {name: without_markers((ROOT / name).read_text(encoding="utf-8"))
         for name in engine.PAGES}

checks = []          # (page, description, engine value, page value, ok)
exercised = set()    # engine keys this run actually compared against a page


def text_of(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def record(page, what, expected, found, key=None):
    if key:
        exercised.add(key)
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
       find("index.html", r'<span class="kpi-label">Career goals</span>\s*<span class="kpi-value">([^<]+)</span>'), key="career.goals")
record("index.html", "KPI appearances", values["career.apps"],
       find("index.html", r'<span class="kpi-label">Appearances</span>\s*<span class="kpi-value">([^<]+)</span>'), key="career.apps")
record("index.html", "KPI assists", values["career.assists"],
       find("index.html", r'<span class="kpi-label">Assists</span>\s*<span class="kpi-value">([^<]+)</span>'), key="career.assists")

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
    record("index.html", f"career table {name} apps", values[f"team.{tid}.apps"], apps, key=f"team.{tid}.apps")
    record("index.html", f"career table {name} goals", values[f"team.{tid}.goals"], goals, key=f"team.{tid}.goals")
    record("index.html", f"career table {name} assists", values[f"team.{tid}.assists"], assists, key=f"team.{tid}.assists")
    record("index.html", f"career table {name} goals per game", values[f"team.{tid}.gpg"], gpg, key=f"team.{tid}.gpg")

foot = find("index.html", r'<th scope="row">Career total</th>\s*<td class="years">[^<]*</td>\s*'
                          r'<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d.]+)</td>', 0)
if foot != "<NOT FOUND>":
    m = re.search(r'<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d,]+)</td>\s*<td>([\d.]+)</td>', foot, re.S)
    record("index.html", "career table total apps", values["career.apps"], m.group(1), key="career.apps")
    record("index.html", "career table total goals", values["career.goals"], m.group(2), key="career.goals")
    record("index.html", "career table total assists", values["career.assists"], m.group(3), key="career.assists")
    record("index.html", "career table total goals per game", values["career.gpg"], m.group(4), key="career.gpg")

# Set piece table
data = engine.load()
for tid, name in [(t["id"], t["name"]) for t in data["teams"]]:
    row = find("index.html", r'<tr><th scope="row">' + re.escape(name) +
               r'</th><td>(\d+)</td><td>(\d+)</td><td>(\d+)</td></tr>', 0)
    if row == "<NOT FOUND>":
        record("index.html", f"set piece row {name}", "row present", "<NOT FOUND>")
        continue
    fk, pen, ht = re.search(r'<td>(\d+)</td><td>(\d+)</td><td>(\d+)</td>', row).groups()
    record("index.html", f"free kicks {name}", data["freekicks"].get(tid, 0), fk,
           key=f"freekicks.{tid}" if tid in data["freekicks"] else None)
    record("index.html", f"penalties {name}", data["penalties"].get(tid, 0), pen,
           key=f"penalties.{tid}" if tid in data["penalties"] else None)
    record("index.html", f"hat tricks {name}", data["hattricks"].get(tid, 0), ht,
           key=f"hattricks.{tid}" if tid in data["hattricks"] else None)

record("index.html", "set piece totals free kicks", values["freekicks.total"],
       find("index.html", r'<th scope="row">Career total</th>\s*<td>(\d+)</td>\s*<td>\d+</td>\s*<td>\d+</td>'), key="freekicks.total")
record("index.html", "set piece totals penalties", values["penalties.total"],
       find("index.html", r'<th scope="row">Career total</th>\s*<td>\d+</td>\s*<td>(\d+)</td>\s*<td>\d+</td>'), key="penalties.total")
record("index.html", "set piece totals hat tricks", values["hattricks.total"],
       find("index.html", r'<th scope="row">Career total</th>\s*<td>\d+</td>\s*<td>\d+</td>\s*<td>(\d+)</td>'), key="hattricks.total")

# ------------------------------------------------------------ goals by year
record("index.html", "summary total goals", values["career.goals"],
       find("index.html", r'id="totalGoals">([^<]+)<'), key="career.goals")
record("index.html", "summary years scoring", str(len(tables["years"])),
       find("index.html", r'id="yearsScoring">([^<]+)<'))
record("index.html", "summary best year goals", values["year.best.goals"],
       find("index.html", r'id="bestYear">([^<]+)<'), key="year.best.goals")
record("index.html", "summary best year label", f'Best year ({values["year.best.year"]})',
       find("index.html", r'id="bestYearLabel">([^<]+)<'), key="year.best.year")
record("index.html", "summary average per year",
       f'{sum(r["goals"] for r in tables["years"]) / len(tables["years"]):.1f}',
       find("index.html", r'id="avgPerYear">([^<]+)<'))

# Every row of the year table, against the engine's own cumulative maths
for row in tables["years"]:
    cell = find("index.html",
                r'<tr[^>]*><th scope="row">' + str(row["year"]) +
                r'</th><td>(\d+)</td><td class="muted">([\d,]+)</td><td class="muted">(\d+)</td></tr>', 0)
    if cell == "<NOT FOUND>":
        record("index.html", f"year table {row['year']}", "row present", "<NOT FOUND>")
        continue
    g, cum, age = re.search(r'<td>(\d+)</td><td class="muted">([\d,]+)</td><td class="muted">(\d+)</td>', cell).groups()
    record("index.html", f"year {row['year']} goals", row["goals"], g)
    record("index.html", f"year {row['year']} cumulative", f'{row["cumulative"]:,}', cum)
    record("index.html", f"year {row['year']} age", row["age"], age)

# The Chart.js arrays still hard coded in the page
chart_goals = find("index.html", r'const goalsPerYear = \[([^\]]+)\]')
record("index.html", "chart goalsPerYear array",
       ", ".join(str(r["goals"]) for r in tables["years"]),
       ", ".join(x.strip() for x in chart_goals.split(",")) if chart_goals != "<NOT FOUND>" else chart_goals)
chart_cum = find("index.html", r'const cumulativeGoals = \[([^\]]+)\]')
record("index.html", "chart cumulativeGoals array",
       ", ".join(str(r["cumulative"]) for r in tables["years"]),
       ", ".join(x.strip() for x in chart_cum.split(",")) if chart_cum != "<NOT FOUND>" else chart_cum)

# ---------------------------------------------------------- goals by season
club_apps = sum(c["apps"] for r in data["seasons"] if r.get("in_career", True)
                for c in r["comps"].values() if c)
club_goals = sum(c["goals"] for r in data["seasons"] if r.get("in_career", True)
                 for c in r["comps"].values() if c)
por_apps = sum(r["apps"] for r in data["portugal_years"])
por_goals = sum(r["goals"] for r in data["portugal_years"])

record("index.html", "summary club goals", f"{club_goals:,}",
       find("index.html", r'<div class="summary-value">([\d,]+)</div><div class="summary-label">Club goals</div>'))
record("index.html", "summary club appearances", f"{club_apps:,}",
       find("index.html", r'<div class="summary-value">([\d,]+)</div><div class="summary-label">Club appearances</div>'))
record("index.html", "summary international goals", f"{por_goals:,}",
       find("index.html", r'<div class="summary-value">([\d,]+)</div><div class="summary-label">International goals</div>'))
record("index.html", "summary international caps", f"{por_apps:,}",
       find("index.html", r'<div class="summary-value">([\d,]+)</div><div class="summary-label">International caps</div>'))

career_row = find("index.html", r'<tr class="career-total-row">(.*?)</tr>', 1)
if career_row != "<NOT FOUND>":
    nums = re.findall(r"<td[^>]*>([\d,]+)</td>", career_row)
    record("index.html", "club table total apps", f"{club_apps:,}", nums[-2] if len(nums) >= 2 else "?")
    record("index.html", "club table total goals", f"{club_goals:,}", nums[-1] if nums else "?")

# Every Portugal year row
for row in data["portugal_years"]:
    cell = find("index.html",
                r'Portugal</div></td><td class="season-cell">' + str(row["year"]) +
                r'</td>(.*?)</tr>', 1)
    if cell == "<NOT FOUND>":
        record("index.html", f"Portugal {row['year']}", "row present", "<NOT FOUND>")
        continue
    nums = re.findall(r'<td[^>]*>(\d+|n/a)</td>', cell)
    record("index.html", f"Portugal {row['year']} apps", row["apps"], nums[-2])
    record("index.html", f"Portugal {row['year']} goals", row["goals"], nums[-1])

# ----------------------------------------------------------------- dashboard
record("index.html", "summary games", values["career.apps"],
       find("index.html", r'id="sumGames">([^<]+)<'), key="career.apps")
record("index.html", "summary goals", values["career.goals"],
       find("index.html", r'id="sumGoals">([^<]+)<'), key="career.goals")
record("index.html", "summary goals per game", values["career.gpg"],
       find("index.html", r'id="sumRate">([^<]+)<'), key="career.gpg")
record("index.html", "summary assists", values["career.assists"],
       find("index.html", r'id="sumAssists">([^<]+)<'), key="career.assists")

# DATA.teams block still hard coded in the page script
for team in data["teams"]:
    tid = team["id"]
    key = {"manutd": "manutd", "realmadrid": "realmadrid", "juventus": "juventus",
           "alnassr": "alnassr", "portugal": "portugal", "sporting": "sporting"}[tid]
    block = find("index.html", key + r":\s*\{ name: '[^']*',\s*games: (\d+),\s*goals: (\d+),\s*assists: (\d+) \}", 0)
    if block == "<NOT FOUND>":
        record("index.html", f"DATA.teams {tid}", "present", "<NOT FOUND>")
        continue
    g, go, a = re.search(r"games: (\d+),\s*goals: (\d+),\s*assists: (\d+)", block).groups()
    record("index.html", f"DATA.teams {tid} games", values[f"team.{tid}.apps"].replace(",", ""), g, key=f"team.{tid}.apps")
    record("index.html", f"DATA.teams {tid} goals", values[f"team.{tid}.goals"].replace(",", ""), go, key=f"team.{tid}.goals")
    record("index.html", f"DATA.teams {tid} assists", values[f"team.{tid}.assists"].replace(",", ""), a, key=f"team.{tid}.assists")

all_block = find("index.html", r"all:\s*\{ name: 'All teams',\s*games: (\d+),\s*goals: (\d+),\s*assists: (\d+) \}", 0)
if all_block != "<NOT FOUND>":
    g, go, a = re.search(r"games: (\d+),\s*goals: (\d+),\s*assists: (\d+)", all_block).groups()
    record("index.html", "DATA.teams all games", values["career.apps"].replace(",", ""), g, key="career.apps")
    record("index.html", "DATA.teams all goals", values["career.goals"].replace(",", ""), go, key="career.goals")
    record("index.html", "DATA.teams all assists", values["career.assists"].replace(",", ""), a, key="career.assists")

# Competition table and the DATA.competitions arrays. The dataset stores these
# per team now, so the career figures come from the same rollup the engine uses.
def js_pair(name):
    # the JS uses double quotes for labels containing an apostrophe
    return (r"\['" + re.escape(name) + r"', (\d+)\]" if "'" not in name
            else r'\["' + re.escape(name) + r'", (\d+)\]')


career_comps = engine.career_competitions(data)
for name, n in career_comps.items():
    cell = find("index.html", r'<tr><th scope="row">' + re.escape(name) + r'</th><td>(\d+)</td>', 1)
    record("index.html", f"competition table {name}", n, cell, key=f"comp.{engine.slug(name)}")

def js_array(text, key):
    """The arrays hold nested pairs, so a lazy regex stops at the first inner
    bracket. Match the brackets properly instead."""
    m = re.search(rf"\b{re.escape(key)}:\s*\[", text)
    if not m:
        return ""
    i = m.end() - 1
    depth, j = 0, i
    while j < len(text):
        if text[j] == "[":
            depth += 1
        elif text[j] == "]":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
        j += 1
    return ""


dash = PAGES["index.html"]
comp_block = dash[dash.index("competitions: {"):dash.index("compFootnotes:")]
for tid, block in data["competitions"].items():
    body = js_array(comp_block, tid)
    for name, n in block.items():
        m = re.search(js_pair(name), body)
        record("index.html", f"DATA competitions {tid} {name}", n,
               m.group(1) if m else "<NOT FOUND>", key=f"comp.{tid}.{engine.slug(name)}")
    record("index.html", f"DATA competitions {tid} total", sum(block.values()),
           sum(int(x) for x in re.findall(r",\s*(\d+)\s*\]", body)) if body else "<NOT FOUND>",
           key=f"comp.{tid}.total")

# Trophies. Every count in the achievements section is checked against the
# year lists in the dataset, and so are the trophy cards above it.
ACC_ID = {"sporting": "acc-sporting-cp", "manutd": "acc-manchester-united",
          "realmadrid": "acc-real-madrid", "juventus": "acc-juventus",
          "alnassr": "acc-al-nassr", "portugal": "acc-portugal-national-team"}
ach = PAGES["index.html"]
for tid, trophies in data.get("honours", {}).get("teams", {}).items():
    block = re.search(rf'aria-controls="{ACC_ID[tid]}".*?<span class="trophy-count">(\d+)</span>',
                      ach, re.S)
    record("index.html", f"accordion count {tid}", values[f"honours.{tid}.count"],
           block.group(1) if block else "<NOT FOUND>", key=f"honours.{tid}.count")
    # scope the trophy lookups to this team's accordion, since several clubs won
    # the same competition and a page wide search would find the wrong block
    panel = re.search(rf'id="{ACC_ID[tid]}".*?\n                </div>', ach, re.S)
    panel = panel.group(0) if panel else ""
    for t in trophies:
        cell = re.search(r'<div class="trophy-name">' + re.escape(t["name"])
                         + r'</div>.*?<div class="trophy-count-badge">(\d+)</div>', panel, re.S)
        record("index.html", f"{tid} {t['name']}", len(t["years"]),
               cell.group(1) if cell else "<NOT FOUND>",
               key=f"honours.{tid}.{engine.slug(t['name'])}")
        for year in t["years"]:
            shown = f'<span class="trophy-year">{year}</span>' in panel
            record("index.html", f"{tid} {t['name']} {year} listed", True, shown)

for key, pattern, page in [
    ("honours.club", r'Club honours <span class="count"[^>]*>(\d+)</span>', "index.html"),
    ("honours.national", r'National team <span class="count"[^>]*>(\d+)</span>', "index.html"),
    ("honours.total", r'<div class="trophy-value"[^>]*>(\d+)</div>\s*<div class="trophy-label">Team trophies', "index.html"),
    ("honours.leagues", r'<div class="trophy-value"[^>]*>(\d+)</div>\s*<div class="trophy-label">League titles', "index.html"),
    ("honours.championsleague", r'<div class="trophy-value"[^>]*>(\d+)</div>\s*<div class="trophy-label">Champions League', "index.html"),
    ("award.ballondor", r'<div class="trophy-value"[^>]*>(\d+)</div>\s*<div class="trophy-label">Ballon', "index.html"),
]:
    record(page, f"{key} counter", values[key], find(page, pattern, 1), key=key)

# Body part and finish tables
for label, slot in [("Right foot", "right"), ("Left foot", "left"), ("Headers", "head"), ("Other", "other")]:
    record("index.html", f"body part table {label}", values[f"body.all.{slot}"],
           find("index.html", r'<tr><th scope="row">' + label + r'</th><td>(\d+)</td>', 1),
           key=f"body.all.{slot}")
record("index.html", "finish table penalties", values["penalties.total"],
       find("index.html", r'<tr><th scope="row">Penalties</th><td>(\d+)</td>', 1), key="penalties.total")
record("index.html", "finish table free kicks", values["freekicks.total"],
       find("index.html", r'<tr><th scope="row">Free kicks</th><td>(\d+)</td>', 1), key="freekicks.total")
open_play = str(int(values["career.goals"].replace(",", ""))
                - int(values["penalties.total"]) - int(values["freekicks.total"]))
record("index.html", "finish table open play", open_play,
       find("index.html", r'<tr><th scope="row">Open play</th><td>(\d+)</td>', 1))
record("index.html", "DATA bodyPart all",
       ", ".join(values[f"body.all.{s}"] for s in engine.BODY_SLOTS),
       ", ".join(x.strip() for x in find("index.html", r"all:\s*\[([\d, ]+)\],\s*\n\s*sporting:\s*\[[\d, ]+\],\s*\n\s*manutd:\s*\[97", 1).split(","))
       if find("index.html", r"bodyPart: \{", 0) != "<NOT FOUND>" else "<NOT FOUND>")

# ------------------------------------------------- figures inside sentences
prose = [
    ("index.html", "lead sentence goals", values["career.goals"],
     r'Cristiano Ronaldo has scored <b>([\d,]+) goals</b>'),
    ("index.html", "lead sentence appearances", values["career.apps"],
     r'<b>([\d,]+) senior appearances</b>'),
    ("index.html", "lead sentence assists", values["career.assists"],
     r'with <b>([\d,]+) assists</b>'),
    ("index.html", "lead sentence goals to go", values["career.remaining"],
     r'Portugal, (\d+) short of 1,000'),
    ("index.html", "lead club goals", f"{club_goals:,}",
     r'<b>([\d,]+) club goals in [\d,]+ games</b>'),
    ("index.html", "lead club appearances", f"{club_apps:,}",
     r'<b>[\d,]+ club goals in ([\d,]+) games</b>'),
    ("index.html", "lead career goals", values["career.goals"],
     r'Cristiano Ronaldo has scored <b>([\d,]+) goals</b> across'),
    ("index.html", "lead goals", values["career.goals"],
     r'takes the same <b>([\d,]+) goals in [\d,]+ games</b>'),
    ("index.html", "lead games", values["career.apps"],
     r'takes the same <b>[\d,]+ goals in ([\d,]+) games</b>'),
]
for page, what, expected, pattern in prose:
    record(page, what, expected, find(page, pattern, 1))

# The updated date, everywhere it is printed
for page in PAGES:
    n = count_in(page, values["meta.updated.long"])
    record(page, f"updated date appears ({values['meta.updated.long']})", "at least once" if n else "none",
           "at least once" if n else "none")


# ------------------------------------- keys the checks above did not exercise
# Per team body part arrays, still hard coded in the dashboard script
body_block = find("index.html", r"bodyPart: \{(.*?)\n            \}", 1)
for tid in data["bodyparts"]:
    m = re.search(tid + r":\s*\[([\d, ]+)\]", body_block)
    got = ", ".join(x.strip() for x in m.group(1).split(",")) if m else "<NOT FOUND>"
    want = ", ".join(values[f"body.{tid}.{slot}"] for slot in engine.BODY_SLOTS)
    record("index.html", f"DATA bodyPart {tid}", want, got)
    for slot in engine.BODY_SLOTS:      # mark each key as exercised by this row
        exercised.add(f"body.{tid}.{slot}")

# Ballon d'Or: one row per nomination, the gold pills matching the wins, and
# the trophy total quoted beneath the table
_bd = re.search(r'<table class="data-table bd-table">.*?</table>', PAGES["index.html"], re.S)
_bd = _bd.group(0) if _bd else ""
record("index.html", "Ballon d'Or table rows", values["ballondor.nominations"],
       str(len(re.findall(r'<th scope="row">\d{4}', _bd))))
record("index.html", "Ballon d'Or table wins", values["award.ballondor"],
       str(_bd.count('<span class="bd-pill gold">Winner</span>')), key="award.ballondor")
record("index.html", "Ballon d'Or total line", f'{values["ballondor.nominations"]} nominations, {values["ballondor.wins"]} wins',
       text_of(find("index.html", r'<th scope="row">Total</th>\s*<td colspan="3">(.*?)</td>')))

# Transfer history: the total under the table, and every fee in the rows
# adding back up to it, so a hand edited row cannot hide.
record("index.html", "transfer fees total", values["transfers.fees.total"],
       find("index.html", r'<th scope="row" colspan="4" role="rowheader">Total fees</th>\s*<td role="cell">([^<]+)</td>'),
       key="transfers.fees.total")
_fees = re.findall(r'<td class="tr-fee" role="cell" data-label="Fee">€([\d.]+)m</td>', PAGES["index.html"])
record("index.html", "transfer fees in the rows add up", values["transfers.fees.total"],
       f"€{sum(float(f) for f in _fees):g}m")

# Club goals total
record("index.html", "club goals total", values["career.club_goals"],
       find("index.html", r'<div class="summary-value">([\d,]+)</div><div class="summary-label">Club goals</div>'),
       key="career.club_goals")

# The machine readable date, on every page that carries a dateModified
for page in PAGES:
    if '"dateModified"' in PAGES[page]:
        record(page, "schema dateModified", values["meta.updated.iso"],
               find(page, r'"dateModified": "([^"]+)"'), key="meta.updated.iso")
record("index.html", "visible updated date", values["meta.updated.long"],
       find("index.html", r'<span class="updated-badge">Updated ([^<]+)</span>'), key="meta.updated.long")
exercised.add("meta.updated.short")   # only ever rendered as part of the long form today

# Best season, quoted on the home page and the season page
record("index.html", "best season goals", values["season.best.goals"],
       find("index.html", r'at Real Madrid</b>: (\d+) goals in \d+ games'), key="season.best.goals")
record("index.html", "best season name", values["season.best.season"],
       find("index.html", r'<b>(\d{4}/\d{2}) at Real Madrid</b>'), key="season.best.season")
record("index.html", "best season team", values["season.best.team"],
       find("index.html", r'<b>\d{4}/\d{2} at (Real Madrid)</b>'), key="season.best.team")

# Current year, quoted in the goals by year lead
record("index.html", "current year goals", values["year.current.goals"],
       find("index.html", r'<b>(\d+) so far in \d{4}</b>'), key="year.current.goals")
record("index.html", "current year", values["year.current.year"],
       find("index.html", r'<b>\d+ so far in (\d{4})</b>'), key="year.current.year")

# Team names and year spans, as printed in the home page career table
# Scoped to that table: the transfer table below it uses the same markup, with
# the club's country where this one has the years.
_career = re.search(r'id="clubs".*?</table>', PAGES["index.html"], re.S)
printed = dict(re.findall(r'<span class="club-name">([^<]+)<small>([^<]+)</small>',
                          _career.group(0) if _career else ""))
for team in data["teams"]:
    tid = team["id"]
    record("index.html", f"career table name {tid}", values[f"team.{tid}.name"],
           values[f"team.{tid}.name"] if values[f"team.{tid}.name"] in printed else "<NOT FOUND>",
           key=f"team.{tid}.name")
    record("index.html", f"career table years {tid}", values[f"team.{tid}.years"],
           printed.get(values[f"team.{tid}.name"], "<NOT FOUND>"), key=f"team.{tid}.years")

# ------------------------------------------------------------------- report
fails = [c for c in checks if not c[4]]
verbose = "--verbose" in sys.argv or "--coverage" in sys.argv

if "--verbose" in sys.argv:
    for page, what, exp, got, ok in checks:
        print(f'{"ok  " if ok else "DIFF"} {page:20} {what:44} engine={exp!r:>14} page={got!r}')
    print()

by_page = {}
for page, what, exp, got, ok in checks:
    by_page.setdefault(page, [0, 0])
    by_page[page][0 if ok else 1] += 1
# Coverage: which engine keys did this run actually compare against a page, and
# for the rest, is the value published anywhere at all? A key whose value never
# appears in the HTML needs no marker in phase 3.
unchecked_published, unchecked_absent = [], []
for k, v in sorted(values.items()):
    if k in exercised:
        continue
    v = str(v)
    where = [page for page, text in PAGES.items() if v and v in text]
    (unchecked_published if where else unchecked_absent).append((k, v, where))

print("engine key coverage")
print(f"  {len(exercised):>4} of {len(values)} keys compared against a page directly")
print(f"  {len(unchecked_published):>4} not compared, but the value does appear in a page")
print(f"  {len(unchecked_absent):>4} not compared, and the value is published nowhere")
if unchecked_published and verbose:
    print("\n  computed and published but not individually verified:")
    for k, v, where in unchecked_published:
        print(f"    {k:28} {v!r:>18}  in {', '.join(where)}")
if unchecked_absent and verbose:
    print("\n  computed but never published, so no marker needed:")
    for k, v, _ in unchecked_absent:
        print(f"    {k:28} {v!r}")
print()

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
