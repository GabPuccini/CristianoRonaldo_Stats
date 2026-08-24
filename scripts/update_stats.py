#!/usr/bin/env python3
"""
ronaldostats.app stat updater.

One command applies a real world event to data/ronaldo.json, recomputes every
derived figure, and rewrites every marked number and table region across all
HTML pages. It validates before it writes, so a bad edit fails loudly instead
of publishing a wrong number.

Typical use:
    python scripts/update_stats.py goal --team alnassr --comp league \
        --opponent "Al Hilal" --body right --type openplay

    python scripts/update_stats.py goal --team portugal --comp "WC quals" \
        --opponent "Hungary" --body head --type openplay --assists 1

    python scripts/update_stats.py appearance --team alnassr --comp league
    python scripts/update_stats.py assist --team alnassr
    python scripts/update_stats.py hattrick --team alnassr
    python scripts/update_stats.py show
    python scripts/update_stats.py build          (rewrite HTML, no data change)
    python scripts/update_stats.py undo           (revert the last event)

Every command except show and build ends by rewriting the HTML.
"""

import argparse
import copy
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ronaldo.json"
BACKUP = ROOT / "data" / "ronaldo.backup.json"

PAGES = [
    "index.html",
    "goalsbyyear.html",
    "goalsbyseason.html",
    "dashboard.html",
    "timeline.html",
    "achievements.html",
]

# Body part slots, in the order they are stored and displayed.
BODY_SLOTS = ["right", "left", "head", "other"]

# Small numbers are spelled out in prose, per the site's writing style.
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
         8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
         14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
         19: "nineteen", 20: "twenty"}


# ----------------------------------------------------------------------------
# Load and save
# ----------------------------------------------------------------------------

def load():
    if not DATA.exists():
        sys.exit(f"Cannot find {DATA}. Run the migration first.")
    with DATA.open(encoding="utf-8") as fh:
        return json.load(fh)


def save(data):
    data["meta"]["updated"] = dt.date.today().isoformat()
    with DATA.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def dashboard_order(data):
    """The dashboard lists teams in career order, clubs first by the year he
    joined and Portugal last, which is how its team picker reads."""
    clubs = [t for t in data["teams"] if t["id"] != "portugal"]
    clubs.sort(key=lambda t: int(t["years"][:4]))
    return [t["id"] for t in clubs] + ["portugal"]


def career_competitions(data):
    """Roll the per team competition tallies up into the labels the overall
    chart publishes, folding the finer ones into Other cup competitions, and
    return them in the order the chart shows: most goals first."""
    rollup = data.get("competition_rollup", {})
    totals = {}
    for block in data["competitions"].values():
        for name, n in block.items():
            name = rollup.get(name, name)
            totals[name] = totals.get(name, 0) + n
    return dict(sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])))


# ----------------------------------------------------------------------------
# Derivation: everything computable is computed, never stored
# ----------------------------------------------------------------------------

def derive(data):
    """Return a flat dict of stat keys to display values, plus table payloads."""
    teams = {t["id"]: t for t in data["teams"]}
    out = {}

    # Club goals and apps come from the season rows so the season page can
    # never drift from the home page.
    club_goals = {tid: 0 for tid in teams}
    club_apps = {tid: 0 for tid in teams}
    for row in data["seasons"]:
        if not row.get("in_career", True):
            continue
        tid = row["team"]
        for comp in row["comps"].values():
            if comp is None:
                continue
            club_goals[tid] = club_goals.get(tid, 0) + comp["goals"]
            club_apps[tid] = club_apps.get(tid, 0) + comp["apps"]

    # Portugal comes from the international year rows.
    for row in data["portugal_years"]:
        club_goals["portugal"] = club_goals.get("portugal", 0) + row["goals"]
        club_apps["portugal"] = club_apps.get("portugal", 0) + row["apps"]

    # Some rows exist on the season page but sit outside the headline career
    # total, for example the Sporting CP B reserve appearances.
    career_goals = sum(club_goals.values())
    career_apps = sum(club_apps.values())
    career_assists = sum(t["assists"] for t in data["teams"])

    target = data["meta"]["goal_target"]
    remaining = target - career_goals
    pct = career_goals / target * 100

    out["career.goals"] = f"{career_goals:,}"
    out["career.goals.raw"] = str(career_goals)
    out["career.apps"] = f"{career_apps:,}"
    out["career.apps.raw"] = str(career_apps)
    out["career.assists"] = f"{career_assists:,}"
    out["career.assists.raw"] = str(career_assists)
    out["career.gpg"] = f"{career_goals / career_apps:.2f}"
    out["career.remaining"] = str(remaining)
    out["career.pct"] = f"{pct:.1f}"
    out["career.target"] = f"{target:,}"
    out["career.progress_label"] = f"{career_goals:,} / {target:,}"
    out["career.fillstyle"] = f"width: {pct:.1f}%;"
    out["career.club_goals"] = f"{sum(v for k, v in club_goals.items() if k != 'portugal'):,}"
    out["career.club_apps"] = f"{sum(v for k, v in club_apps.items() if k != 'portugal'):,}"
    pens_all = sum(data["penalties"].values())
    fks_all = sum(data["freekicks"].values())
    out["career.openplay"] = f"{career_goals - pens_all - fks_all:,}"
    # everything that was not a penalty, i.e. open play plus direct free kicks
    out["career.nonpenalty"] = f"{career_goals - pens_all:,}"
    out["career.penalty_pct"] = f"{pens_all / career_goals * 100:.1f}"
    out["career.openplay_pct"] = f"{(career_goals - pens_all - fks_all) / career_goals * 100:.1f}"
    # the dashboard writes "just over N percent", so it wants the whole number below
    out["career.openplay_pct_round"] = str(
        int((career_goals - pens_all - fks_all) / career_goals * 100))

    # Per team figures
    for tid, team in teams.items():
        g = club_goals.get(tid, 0)
        a = club_apps.get(tid, 0)
        out[f"team.{tid}.goals"] = f"{g:,}"
        out[f"team.{tid}.apps"] = f"{a:,}"
        out[f"team.{tid}.assists"] = f"{team['assists']:,}"
        out[f"team.{tid}.gpg"] = f"{g / a:.2f}" if a else "0.00"
        out[f"team.{tid}.name"] = team["name"]
        out[f"team.{tid}.years"] = team["years"]

    # Set pieces and hat tricks
    for group in ("penalties", "freekicks", "hattricks"):
        block = data[group]
        out[f"{group}.total"] = f"{sum(block.values()):,}"
        for tid in teams:                       # a team on zero still needs a key
            out[f"{group}.{tid}"] = f"{block.get(tid, 0):,}"

    # Open play is whatever is left once the set pieces are taken out
    for tid in teams:
        out[f"openplay.{tid}"] = str(
            club_goals.get(tid, 0)
            - data["penalties"].get(tid, 0)
            - data["freekicks"].get(tid, 0))

    # Body parts, career and per team
    totals = [0, 0, 0, 0]
    for tid, slots in data["bodyparts"].items():
        for i, n in enumerate(slots):
            totals[i] += n
        for i, slot in enumerate(BODY_SLOTS):
            out[f"body.{tid}.{slot}"] = str(slots[i])
    for i, slot in enumerate(BODY_SLOTS):
        out[f"body.all.{slot}"] = str(totals[i])

    # Competitions. The dataset stores them per team, with a finer set of labels
    # than the overall chart publishes, so the career figures are rolled up here
    # and a goal recorded against a team moves both charts at once.
    for tid, block in data["competitions"].items():
        for name, n in block.items():
            out[f"comp.{tid}.{slug(name)}"] = str(n)
        out[f"comp.{tid}.total"] = str(sum(block.values()))
    for name, n in career_competitions(data).items():
        out[f"comp.{slug(name)}"] = str(n)

    # Trophies and awards. Every count on the site is the length of a year list,
    # so adding a trophy in one place moves the counters, the accordions, the
    # filter tabs and the prose together.
    hon = data.get("honours", {})
    teams_hon = hon.get("teams", {})
    LEAGUES = {"Premier League", "La Liga", "Serie A", "Saudi Pro League", "Primeira Liga"}
    club_total = national_total = 0
    for tid, trophies in teams_hon.items():
        n = sum(len(t["years"]) for t in trophies)
        out[f"honours.{tid}.count"] = str(n)
        out[f"honours.{tid}.kinds"] = str(len(trophies))
        for t in trophies:
            out[f"honours.{tid}.{slug(t['name'])}"] = str(len(t["years"]))
        if tid == "portugal":
            national_total += n
        else:
            club_total += n
    out["honours.club"] = str(club_total)
    out["honours.national"] = str(national_total)
    out["honours.total"] = str(club_total + national_total)
    out["honours.leagues"] = str(sum(
        len(t["years"]) for v in teams_hon.values() for t in v if t["name"] in LEAGUES))
    out["honours.championsleague"] = str(sum(
        len(t["years"]) for v in teams_hon.values() for t in v
        if t["name"] == "UEFA Champions League"))
    for award in hon.get("individual", []):
        out[f"award.{slug(award['name'])}"] = str(award["count"])
    # Opponent tallies, so a figure quoted in prose comes off the same lists the
    # dashboard's opponent card is built from.
    for group, block in data.get("opponents", {}).items():
        for name, n in block.items():
            out[f"opponent.{group}.{slug(name)}.goals"] = str(n)
    for group, block in data.get("opponent_apps", {}).items():
        for name, n in block.items():
            out[f"opponent.{group}.{slug(name)}.apps"] = str(n)

    if "individual_floor" in hon:
        out["award.floor"] = str(hon["individual_floor"])
        out["award.floor_plus"] = f"{hon['individual_floor']}+"

    # Calendar years, with the running career total recomputed every time
    running = 0
    year_rows = []
    for row in sorted(data["years"], key=lambda r: r["year"]):
        running += row["goals"]
        year_rows.append({**row, "cumulative": running})
    best_year = max(year_rows, key=lambda r: r["goals"])
    out["year.best.goals"] = str(best_year["goals"])
    out["year.best.year"] = str(best_year["year"])
    out["year.current.goals"] = str(year_rows[-1]["goals"])
    out["year.current.year"] = str(year_rows[-1]["year"])
    out["year.count"] = str(len(year_rows))
    out["year.average"] = f"{sum(r['goals'] for r in year_rows) / len(year_rows):.1f}"
    for row in year_rows:
        out[f"year.{row['year']}.goals"] = str(row["goals"])
        out[f"year.{row['year']}.cumulative"] = f"{row['cumulative']:,}"
        out[f"year.{row['year']}.age"] = str(row["age"])
    # the sparkline's aria-label is the only description a screen reader gets,
    # so it is composed here rather than left to drift
    best = max(year_rows, key=lambda r: r["goals"])
    cur = year_rows[-1]
    out["spark.label"] = (
        "Bar chart of Cristiano Ronaldo goals in each calendar year from "
        f"{year_rows[0]['year']} to {cur['year']}, peaking at {best['goals']} goals "
        f"in {best['year']} and standing at {cur['goals']} goals so far in {cur['year']}")
    out["year.first"] = str(year_rows[0]["year"])
    out["year.first.goals"] = str(year_rows[0]["goals"])
    out["year.last"] = str(year_rows[-1]["year"])
    out["year.span"] = f"{year_rows[0]['year']} to {year_rows[-1]['year']}"
    # the pages say "40 goals or more in N separate years", both as a figure and
    # spelled out, so both forms are computed from the same count
    above40 = sum(1 for r in year_rows if r["goals"] >= 40)
    out["year.above40"] = str(above40)
    out["year.above40.word"] = WORDS.get(above40, str(above40))
    out["year.above40.threshold"] = "40"
    # The prose ranks his best years, and names the year each round hundred was
    # passed, so both come off the same rows rather than being remembered.
    for rank, row in enumerate(sorted(year_rows, key=lambda r: -r["goals"])[:5], start=1):
        out[f"year.rank{rank}.goals"] = str(row["goals"])
        out[f"year.rank{rank}.year"] = str(row["year"])
    for milestone in range(100, career_goals + 1, 100):
        hit = next(r for r in year_rows if r["cumulative"] >= milestone)
        out[f"milestone.{milestone}.year"] = str(hit["year"])

    # Seasons, best club campaign
    season_totals = []
    for row in data["seasons"]:
        if not row.get("in_career", True):
            continue
        g = sum(c["goals"] for c in row["comps"].values() if c)
        a = sum(c["apps"] for c in row["comps"].values() if c)
        season_totals.append({"season": row["season"], "team": row["team"], "goals": g, "apps": a})
    best_season = max(season_totals, key=lambda r: r["goals"])
    out["season.best.goals"] = str(best_season["goals"])
    out["season.best.season"] = best_season["season"]
    out["season.best.team"] = teams[best_season["team"]]["name"]
    out["season.best.apps"] = str(best_season["apps"])
    # The prose ranks his best campaigns and names his best at each club, so
    # both come off the season rows rather than being remembered by hand.
    by_goals = sorted(season_totals, key=lambda r: (-r["goals"], r["season"]))
    for rank, row in enumerate(by_goals[:8], start=1):
        out[f"season.rank{rank}.goals"] = str(row["goals"])
        out[f"season.rank{rank}.season"] = row["season"]
        out[f"season.rank{rank}.team"] = teams[row["team"]]["name"]
    league_of = {}
    for row in data["seasons"]:
        if not row.get("in_career", True):
            continue
        cell = row["comps"].get("league")
        league_of[(row["team"], row["season"])] = cell["goals"] if cell else 0
    # keyed by the season label as the pages print it, so prose and structured
    # data can name a campaign directly
    for row in season_totals:
        tag = row["season"].replace("/", "-")
        out[f"season.{tag}.{row['team']}.goals"] = str(row["goals"])
        out[f"season.{tag}.{row['team']}.apps"] = str(row["apps"])
    out["season.best.league_goals"] = str(
        league_of.get((best_season["team"], best_season["season"]), 0))
    for tid in teams:
        rows = [r for r in season_totals if r["team"] == tid]
        if not rows:
            continue
        top = max(rows, key=lambda r: r["goals"])
        out[f"team.{tid}.bestseason.goals"] = str(top["goals"])
        out[f"team.{tid}.bestseason.season"] = top["season"]

    # Season table cells, one key per published cell, so the season page can be
    # driven without regenerating any of its markup.
    slots = ["league", "cup", "lcup", "cont", "other"]
    club_col = {s: [0, 0] for s in slots}
    spell, spells = None, []
    for i, row in enumerate(data["seasons"]):
        r_apps = r_goals = 0
        for slot in slots:
            cell = row["comps"].get(slot)
            if cell is None:
                out[f"season.{i}.{slot}.apps"] = "n/a"
                out[f"season.{i}.{slot}.goals"] = "n/a"
                continue
            out[f"season.{i}.{slot}.apps"] = str(cell["apps"])
            out[f"season.{i}.{slot}.goals"] = str(cell["goals"])
            r_apps += cell["apps"]
            r_goals += cell["goals"]
        out[f"season.{i}.total.apps"] = f"{r_apps:,}"
        out[f"season.{i}.total.goals"] = f"{r_goals:,}"
        if not row.get("in_career", True):
            continue
        for slot in slots:
            cell = row["comps"].get(slot)
            if cell:
                club_col[slot][0] += cell["apps"]
                club_col[slot][1] += cell["goals"]
        # a spell is a run of consecutive seasons at the same club
        if spell is None or spell["team"] != row["team"]:
            spell = {"team": row["team"], "cols": {s: [0, 0] for s in slots}}
            spells.append(spell)
        for slot in slots:
            cell = row["comps"].get(slot)
            if cell:
                spell["cols"][slot][0] += cell["apps"]
                spell["cols"][slot][1] += cell["goals"]

    for n, sp in enumerate(spells):
        t_apps = sum(v[0] for v in sp["cols"].values())
        t_goals = sum(v[1] for v in sp["cols"].values())
        for slot in slots:
            out[f"spell.{n}.{slot}.apps"] = f'{sp["cols"][slot][0]:,}'
            out[f"spell.{n}.{slot}.goals"] = f'{sp["cols"][slot][1]:,}'
        out[f"spell.{n}.total.apps"] = f"{t_apps:,}"
        out[f"spell.{n}.total.goals"] = f"{t_goals:,}"

    for slot in slots:
        out[f"club.total.{slot}.apps"] = f"{club_col[slot][0]:,}"
        out[f"club.total.{slot}.goals"] = f"{club_col[slot][1]:,}"

    # Portugal year rows, competitive and friendly and the totals. A year with
    # no matches of one kind prints n/a rather than a zero, which is what the
    # season page already does.
    for row in data["portugal_years"]:
        y = row["year"]
        out[f"portugal.{y}.apps"] = str(row["apps"])
        out[f"portugal.{y}.goals"] = str(row["goals"])
        for kind in ("competitive", "friendly"):
            cell = row.get(kind) or [None, None]
            for i, what in enumerate(("apps", "goals")):
                out[f"portugal.{y}.{kind}.{what}"] = (
                    "n/a" if cell[i] is None else str(cell[i]))
    for kind in ("competitive", "friendly"):
        for i, what in enumerate(("apps", "goals")):
            out[f"portugal.{kind}.{what}"] = str(sum(
                (r.get(kind) or [0, 0])[i] or 0 for r in data["portugal_years"]))

    # Current season, as quoted on the home page and the season page
    cur = data["meta"]["current_season"]
    cur_rows = [r for r in data["seasons"] if r["season"] == cur and r.get("in_career", True)]
    if cur_rows:
        cg = sum(c["goals"] for r in cur_rows for c in r["comps"].values() if c)
        out["season.current.name"] = cur
        out["season.current.goals"] = str(cg)
        out["season.current.league_goals"] = str(sum(
            r["comps"]["league"]["goals"] for r in cur_rows if r["comps"].get("league")))
    out["season.count"] = str(len({r["season"] for r in data["seasons"] if r.get("in_career", True)}))
    out["career.assist_rate"] = f"{career_apps / career_assists:.1f}" if career_assists else "0.0"

    # Identity, derived from the date of birth so the age never goes stale
    born = dt.date.fromisoformat(data["meta"]["born"])
    asof = dt.date.fromisoformat(data["meta"]["updated"])
    out["person.age"] = str(asof.year - born.year - ((asof.month, asof.day) < (born.month, born.day)))
    out["person.born.long"] = f"{born.day} {born:%B %Y}"
    out["person.born.iso"] = born.isoformat()

    # Dates
    updated = dt.date.fromisoformat(data["meta"]["updated"])
    out["meta.updated.iso"] = updated.isoformat()
    out["meta.updated.long"] = f"{updated.day} {updated:%B %Y}"
    out["meta.updated.short"] = f"{updated:%B %Y}"
    # the timeline's key dates list uses an abbreviated month
    out["meta.updated.compact"] = f"{updated.day} {updated:%b %Y}"
    # The header badge is an inline-flex row with a gap, so marking the date on
    # its own would turn it into a third flex item and widen the pill. The whole
    # label is one marker instead, which keeps the badge exactly as it renders.
    out["meta.updated.badge"] = f"Updated {updated.day} {updated:%B %Y}"

    tables = {
        "years": year_rows,
        "seasons": data["seasons"],
        "portugal_years": data["portugal_years"],
        "season_chart": season_totals,
    }
    return out, tables, {
        "career_goals": career_goals,
        "career_apps": career_apps,
        "career_assists": career_assists,
        "club_goals": club_goals,
        "club_apps": club_apps,
        "body_totals": totals,
        "year_rows": year_rows,
    }


def slug(name):
    return re.sub(r"[^a-z0-9]+", "", name.lower())


# ----------------------------------------------------------------------------
# Validation: refuse to publish a dataset that does not reconcile
# ----------------------------------------------------------------------------

def validate(data, facts):
    errors = []
    cg = facts["career_goals"]

    year_sum = sum(r["goals"] for r in data["years"])
    if year_sum != cg:
        errors.append(f"calendar years sum to {year_sum}, career goals are {cg}")

    body_sum = sum(facts["body_totals"])
    if body_sum != cg:
        errors.append(f"body part splits sum to {body_sum}, career goals are {cg}")

    comp_sum = sum(career_competitions(data).values())
    if comp_sum != cg:
        errors.append(f"competitions sum to {comp_sum}, career goals are {cg}")

    # Each team's competitions must also account for exactly that team's goals,
    # otherwise the dashboard charts drift away from the tables.
    for tid, block in data["competitions"].items():
        team_goals = facts["club_goals"].get(tid, 0)
        if sum(block.values()) != team_goals:
            errors.append(
                f"competitions for {tid} sum to {sum(block.values())}, "
                f"that team has {team_goals} goals")

    for tid, slots in data["bodyparts"].items():
        team_goals = facts["club_goals"].get(tid, 0)
        if sum(slots) != team_goals:
            errors.append(
                f"body parts for {tid} sum to {sum(slots)}, that team has {team_goals} goals")

    # Trophies must belong to a team the site knows about, and every trophy must
    # carry the years it was won, since the counts are those lists' lengths.
    known = {t["id"] for t in data["teams"]}
    for tid, trophies in data.get("honours", {}).get("teams", {}).items():
        if tid not in known:
            errors.append(f"honours listed for unknown team {tid}")
        for t in trophies:
            if not t.get("years"):
                errors.append(f"{tid} trophy {t.get('name', '?')} has no years")
            if len(set(t["years"])) != len(t["years"]):
                errors.append(f"{tid} trophy {t['name']} repeats a year")

    # The Portugal split must add back up to each year's total, or the season
    # page's competitive and friendly columns drift away from its total column.
    for row in data["portugal_years"]:
        a = sum((row.get(k) or [0, 0])[0] or 0 for k in ("competitive", "friendly"))
        g = sum((row.get(k) or [0, 0])[1] or 0 for k in ("competitive", "friendly"))
        if a != row["apps"] or g != row["goals"]:
            errors.append(
                f"Portugal {row['year']}: split is {a} apps and {g} goals, "
                f"the row totals {row['apps']} and {row['goals']}")

    pens = sum(data["penalties"].values())
    fks = sum(data["freekicks"].values())
    if pens + fks > cg:
        errors.append(f"penalties plus free kicks ({pens + fks}) exceed career goals ({cg})")

    for tid in data["penalties"]:
        team_goals = facts["club_goals"].get(tid, 0)
        combined = data["penalties"].get(tid, 0) + data["freekicks"].get(tid, 0)
        if combined > team_goals:
            errors.append(f"set pieces for {tid} ({combined}) exceed that team's {team_goals} goals")

    # Opponent lists are keyed by the group name the dashboard publishes, so map
    # each one back to the team it belongs to before comparing. Keying by team id
    # meant the saudi, intl and club groups were never checked at all.
    group_team = {group: tid for tid, group in OPPONENT_GROUP.items()}
    for group, block in data.get("opponents", {}).items():
        if group not in group_team and group != OPPONENT_AGGREGATE:
            errors.append(f"opponent group {group} is not one the site publishes")
            continue
        total = sum(block.values())
        if group == OPPONENT_AGGREGATE:
            team_goals = sum(v for k, v in facts["club_goals"].items() if k != "portugal")
        else:
            team_goals = facts["club_goals"].get(group_team[group], 0)
        if team_goals and total > team_goals:
            errors.append(f"opponent goals for {group} sum to {total}, above the {team_goals} available")
        # Goals are deliberately not compared against appearances here: a hat
        # trick is three goals in one game, and the Juventus list has several.
        apps = data.get("opponent_apps", {}).get(group, {})
        for name in block:
            if apps and name not in apps:
                errors.append(f"{group}: {name} has goals recorded but no appearances")

    return errors


# ----------------------------------------------------------------------------
# HTML rewriting
# ----------------------------------------------------------------------------

VALUE_RE = re.compile(
    r'<(?P<tag>[a-zA-Z0-9]+)(?P<attrs>[^>]*?\sdata-stat(?:-attr)?="[^"]*"[^>]*?)>'
    r'(?P<body>.*?)</(?P=tag)>',
    re.DOTALL,
)
KEY_RE = re.compile(r'\sdata-stat="([^"]+)"')
# Regions are delimited by an HTML comment in markup, or a // comment inside a
# script block, where an HTML comment would be legacy syntax.
REGION_RE = re.compile(
    # [ \t]* rather than \s*, so the marker never swallows the newline after it
    r"(?P<open>(?:<!--|//)[ \t]*STATS:BEGIN[ \t]+(?P<key>[\w.]+)[ \t]*(?:-->)?)"
    r"(?P<body>.*?)"
    r"(?P<close>(?:<!--|//)[ \t]*STATS:END[ \t]+(?P=key)[ \t]*(?:-->)?)",
    re.DOTALL,
)
ATTR_SPEC_RE = re.compile(r'data-stat-attr="([^"]+)"')

# ----------------------------------------------------------------------------
# Text rules: figures with nowhere to hang a marker
#
# Titles, meta descriptions, JSON-LD strings and CSS declarations cannot carry a
# data-stat attribute, and wrapping them in a span either shows up in the page
# or breaks the JSON. They are rewritten by pattern instead.
#
# Each rule is (pattern, key). The pattern must have exactly one capturing
# group, which is the text replaced by the key's value. Rules are checked on
# every build: a pattern that stops matching, or matches more than once, is
# reported rather than silently skipped, so an edit to the prose cannot quietly
# strand a figure.
# ----------------------------------------------------------------------------

try:
    from head_rules import RULES as GENERATED_HEAD_RULES
except ImportError:                                   # generated file not present
    GENERATED_HEAD_RULES = {}


def text_rules(generated=True):
    G = r"([\d,]+)"                       # a figure, with or without a comma
    D = r"(\d{1,2} \w+ \d{4})"            # a long date, e.g. 26 July 2026
    common = [
        (r'"dateModified": "(\d{4}-\d\d-\d\d)"', "meta.updated.iso"),
    ]
    table = {
        "index.html": common + [
            (r"as of " + D + r"[.,]", "meta.updated.long", 8),
            (r"has " + G + r" career goals, [\d,]+ assists", "career.goals", 2),
            (r"career goals, " + G + r" assists and [\d,]+ appearances", "career.assists", 2),
            (r"assists and " + G + r" appearances as of", "career.apps", 4),
            (r'content="' + G + r" goals, [\d,]+ assists", "career.goals", 2),
            (r'content="[\d,]+ goals, ' + G + r" assists", "career.assists", 2),
            (r'content="[\d,]+ goals, [\d,]+ assists and ' + G + r" appearances", "career.apps", 2),
            (r"Cristiano Ronaldo is " + G + r" years old", "person.age"),
            (r"for Real Madrid, " + G + r" for Manchester United and [\d,]+ for Juventus",
             "comp.manutd.championsleague"),
            (r"history of the competition: [\d,]+ for Real Madrid, [\d,]+ for Manchester "
             r"United and " + G + r" for Juventus", "comp.juventus.championsleague"),
            (r"free kick goals: [\d,]+ for Real Madrid, [\d,]+ for Manchester United, "
             r"[\d,]+ for Portugal, [\d,]+ for Al Nassr and " + G + r" for Juventus",
             "freekicks.juventus"),
            (r"[\d,]+ for Portugal, " + G + r" for Al Nassr and [\d,]+ for Juventus",
             "freekicks.alnassr"),
            (r"hat tricks, [\d,]+ of them for Real Madrid, [\d,]+ for Portugal, [\d,]+ for "
             r"Al Nassr, [\d,]+ for Manchester United and " + G + r" for Juventus",
             "hattricks.juventus"),
            (r"hat tricks, " + G + r" of them for Real Madrid", "hattricks.realmadrid"),
            (r"of them for Real Madrid, " + G + r" for Portugal, [\d,]+ for Al Nassr",
             "hattricks.portugal"),
            (r"for Portugal, " + G + r" for Al Nassr, [\d,]+ for Manchester United",
             "hattricks.alnassr"),
            (r"for Al Nassr, " + G + r" for Manchester United and [\d,]+ for Juventus\.",
             "hattricks.manutd"),
            (r"free kick goals: [\d,]* ?for Real Madrid, " + G + r" for Manchester United",
             "freekicks.manutd"),
            (r"for Manchester United, " + G + r" for Portugal, [\d,]* ?for Al Nassr",
             "freekicks.portugal"),
            (r"\.progress-fill \{ width: ([\d.]+)% !important; \}", "career.pct"),
            (r"\.progress-fill \{\n            height: 100%;\n            width: ([\d.]+)%;", "career.pct"),
        ],
        "goalsbyyear.html": common + [
            (r"as of " + D + r"[.,]", "meta.updated.long", 3),
            (r"Ronaldo Goals by Year: " + G + r" Career Goals", "career.goals", 4),
            (r"goals by year: " + G + r" in his best year", "year.best.goals", 2),
            (r"in his best year, " + G + r" so far in", "year.current.goals", 2),
            (r"so far in \d{4} and " + G + r" in total", "career.goals", 2),
            (r"cumulative climb to " + G + r", from", "career.goals"),
            (r"to a best of " + G + r" in \d{4}\. Updated", "year.best.goals"),
            (r"climb to " + G + r", with a best of", "career.goals"),
            (r"with a best of " + G + r" goals in", "year.best.goals"),
        ],
        "goalsbyseason.html": common + [
            (r"as of " + D + r"[.,]", "meta.updated.long", 3),
            (r"season by season: " + G + r" club goals", "career.club_goals", 2),
            (r"club goals in " + G + r" games and", "career.club_apps", 2),
            (r"games and " + G + r" for Portugal in", "team.portugal.goals", 2),
            (r"for Portugal in " + G + r" caps", "team.portugal.apps", 2),
            (r"year by year: " + G + r" club goals,", "career.club_goals"),
            (r"club goals, " + G + r" international goals", "team.portugal.goals"),
            (r"best season of " + G + r" goals in", "season.best.goals"),
        ],
        "dashboard.html": common + [
            (r"as of " + D + r"[.,]", "meta.updated.long", 2),
            (r"Ronaldo's " + G + r" goals by team", "career.goals", 2),
            (r"dashboard follows: " + G + r" career goals by competition", "career.goals"),
            (r'twitter:description" content="' + G + r" career goals by competition", "career.goals"),
            (r"finish type as of [^:]*: " + G + r" in La Liga", "comp.laliga"),
        ],
        "timeline.html": common + [
            (r"Updated " + D + r"\.", "meta.updated.long"),
            (r"debut at \d+ to " + G + r" career goals, milestone by milestone and dated\. Updated", "career.goals"),
            (r"debut at \d+ to " + G + r" career goals, milestone by milestone and dated\.\"", "career.goals"),
            (r'"description": "' + G + r' career goals and counting', "career.goals"),
            (r"The last great number is " + G + r" away\.", "career.remaining"),
            (r"scored " + G + r" goals in [\d,]+ games\.", "team.realmadrid.goals"),
            (r"scored [\d,]+ goals in " + G + r" games\.", "team.realmadrid.apps"),
            (r"As of " + D + r" he has", "meta.updated.long"),
            (r"he has " + G + r" career goals, [\d,]+ short of", "career.goals"),
            (r"career goals, " + G + r" short of [\d,]+\.", "career.remaining"),
            (r"short of " + G + r'\."', "career.target"),
            (r"At " + G + r" he is still playing", "person.age"),
        ],
        "achievements.html": common + [
            (r"as of " + D + r"[.,]", "meta.updated.long", 5),
            (r"Ronaldo Trophies and Awards: " + G + r" Titles", "honours.total", 4),
            (r"has won " + G + r" team trophies, including", "honours.total", 2),
            (r"including " + G + r" Champions Leagues and Euro", "honours.championsleague", 3),
            (r"Euro 2016, plus " + G + r" Ballon d'Or awards", "award.ballondor", 2),
            (r"Ballon d'Or and more than " + G + r" individual awards", "award.floor", 2),
            (r'content="' + G + r" team trophies including", "honours.total"),
            (r"team trophies including " + G + r" Champions Leagues", "honours.championsleague"),
            (r'content="' + G + r" team trophies, [\d,]+ Champions Leagues", "honours.total"),
            (r"team trophies, " + G + r" Champions Leagues, Euro", "honours.championsleague"),
            (r"Euro 2016, " + G + r" Ballon d'Or and more than", "award.ballondor"),
            (r'"description": "The ' + G + r" team trophies Cristiano Ronaldo has won", "honours.total"),
            (r"has won " + G + r" team trophies as of", "honours.total"),
            (r"team trophies as of \d{1,2} \w+ \d{4}: " + G + r" at club level", "honours.club"),
            (r"at club level with .*?, and " + G + r" with Portugal\.", "honours.national"),
            (r"Champions League " + G + r" times: once with Manchester", "honours.championsleague"),
            (r"has won " + G + r" Ballon d'Or awards, in", "award.ballondor"),
            (r"has won " + G + r" league titles in four countries", "honours.leagues"),
            (r'"Real Madrid: ' + G + r" trophies, including", "honours.realmadrid.count"),
            (r"Real Madrid, with " + G + r" trophies in nine seasons", "honours.realmadrid.count"),
            (r"of the Year awards and " + G + r" selections in the FIFA", "award.fifafifproworld11"),
        ],
    }
    # The rest of the head is generated: see scripts/gen_head_rules.py. The
    # generator passes generated=False so it never reads back its own output.
    for page, extra in (GENERATED_HEAD_RULES if generated else {}).items():
        table.setdefault(page, []).extend(extra)
    return table


def script_rules():
    """Prose that lives inside a JavaScript string literal, where neither a
    marker nor a region fits. Same contract as text_rules, but applied to the
    body rather than the head."""
    G = r"([\d,]+)"
    return {
        "dashboard.html": [
            (r"Lists like the " + G + r" against Atletico Madrid", "opponent.club.atleticomadrid.goals", 2),
            (r"a total such as the " + G + r" against Atletico Madrid", "opponent.club.atleticomadrid.goals"),
            (r"His " + G + r" World Cup goals include three", "comp.portugal.worldcup"),
            (r"All " + G + r" across the whole career", "career.goals"),
            # the provenance comment above DATA quotes the total it reconciles to
            (r"which reconciles exactly with the " + G + r" total here", "career.goals"),
            (r"published on ronaldostats\.app, updated ([A-Z][a-z]+ \d{4})", "meta.updated.short"),
            (r"body part figures come from the MessivsRonaldo\.app database,\n"
             r"        // ([A-Z][a-z]+ \d{4}),", "meta.updated.short"),
        ],
    }


def apply_text_rules(text, page, values, report):
    """Apply this page's text rules. A rule may be (pattern, key) for a figure
    that appears once, or (pattern, key, n) for one that is repeated verbatim,
    typically a title that is also the og and twitter title. The count is an
    assertion: if the page stops matching it, the build says so rather than
    leaving the figure behind."""
    # Rules only ever rewrite the head: the title, the meta descriptions, the
    # JSON-LD and the stylesheet. The body belongs to the marker mechanism, and
    # keeping the two apart means they can never fight over the same figure.
    split = text.find("</head>")
    if split == -1:
        return text
    head, body = text[:split], text[split:]
    for rule in text_rules().get(page, []):
        pattern, key = rule[0], rule[1]
        expected = rule[2] if len(rule) > 2 else 1
        if key not in values:
            report["missing"].add(key)
            continue
        hits = list(re.finditer(pattern, head))
        if len(hits) != expected:
            report["rules"].append(
                f"{page}: expected {expected} match(es) for {key}, found "
                f"{len(hits)} <- {pattern}")
            continue
        for m in reversed(hits):            # right to left, so offsets hold
            head = head[:m.start(1)] + values[key] + head[m.end(1):]
        report["texts"] += len(hits)

    for rule in script_rules().get(page, []):
        pattern, key = rule[0], rule[1]
        expected = rule[2] if len(rule) > 2 else 1
        if key not in values:
            report["missing"].add(key)
            continue
        hits = list(re.finditer(pattern, body))
        if len(hits) != expected:
            report["rules"].append(
                f"{page}: expected {expected} script match(es) for {key}, found "
                f"{len(hits)} <- {pattern}")
            continue
        for m in reversed(hits):
            body = body[:m.start(1)] + values[key] + body[m.end(1):]
        report["texts"] += len(hits)

    return head + body



def rewrite_page(text, values, regions, report):
    def value_sub(m):
        attrs = m.group("attrs")
        key_match = KEY_RE.search(attrs)
        key = key_match.group(1) if key_match else None
        if key is not None and key not in values:
            report["missing"].add(key)
            return m.group(0)
        spec = ATTR_SPEC_RE.search(attrs)
        if spec:
            for pair in spec.group(1).split(","):
                if ":" not in pair:
                    continue
                attr_name, attr_key = pair.split(":", 1)
                attr_name, attr_key = attr_name.strip(), attr_key.strip()
                if attr_key not in values:
                    report["missing"].add(attr_key)
                    continue
                if re.search(rf'\s{re.escape(attr_name)}="[^"]*"', attrs):
                    attrs = re.sub(
                        rf'\s{re.escape(attr_name)}="[^"]*"',
                        f' {attr_name}="{values[attr_key]}"',
                        attrs, count=1,
                    )
                else:
                    attrs += f' {attr_name}="{values[attr_key]}"'
                report["attrs"] += 1
        body = m.group("body")
        if key is None:
            # An attribute only marker leaves the body alone, but the body may
            # hold markers of its own, and the outer match has already consumed
            # them, so descend rather than passing them through untouched.
            body = VALUE_RE.sub(value_sub, body)
        else:
            if KEY_RE.search(body):
                report["nested"].append(f"{key} wraps another marker, which it would erase")
            body = values[key]
            report["values"] += 1
        return f'<{m.group("tag")}{attrs}>{body}</{m.group("tag")}>'

    def region_sub(m):
        key = m.group("key")
        if key not in regions:
            report["missing"].add("region:" + key)
            return m.group(0)
        report["regions"] += 1
        # Put the closing marker back at the same indentation as the opening one,
        # otherwise every build shunts it to column zero.
        line_start = text.rfind("\n", 0, m.start("open")) + 1
        indent = text[line_start:m.start("open")]
        indent = indent if indent.strip() == "" else ""
        return f'{m.group("open")}\n{regions[key]}\n{indent}{m.group("close")}'

    text = VALUE_RE.sub(value_sub, text)
    text = REGION_RE.sub(region_sub, text)
    return text


def build_regions(data, tables, values):
    teams = {t["id"]: t for t in data["teams"]}
    r = {}

    # Calendar year table body. The markup here must match the page exactly:
    # the running total and age cells are muted, and the best year is highlighted.
    best = max(row["goals"] for row in tables["years"])
    rows = []
    for row in tables["years"]:
        cls = ' class="peak"' if row["goals"] == best else ""
        rows.append(
            f'                                <tr{cls}>'
            f'<th scope="row">{row["year"]}</th>'
            f'<td>{row["goals"]}</td>'
            f'<td class="muted">{row["cumulative"]:,}</td>'
            f'<td class="muted">{row["age"]}</td>'
            "</tr>"
        )
    r["table.years"] = "\n".join(rows)

    # Portugal year table body
    rows = []
    for row in tables["portugal_years"]:
        rows.append(
            "                            <tr>"
            f'<th scope="row">{row["year"]}</th>'
            f'<td>{row["apps"]}</td>'
            f'<td>{row["goals"]}</td>'
            "</tr>"
        )
    r["table.portugal_years"] = "\n".join(rows)

    # Career at a glance table body, ordered by goals
    order = sorted(
        (t for t in data["teams"]),
        key=lambda t: int(values[f'team.{t["id"]}.goals'].replace(",", "")),
        reverse=True,
    )
    rows = []
    for t in order:
        tid = t["id"]
        rows.append(
            "                            <tr>"
            f'<th scope="row">{t["name"]}<span class="years">{t["years"]}</span></th>'
            f'<td>{values[f"team.{tid}.apps"]}</td>'
            f'<td>{values[f"team.{tid}.goals"]}</td>'
            f'<td>{values[f"team.{tid}.assists"]}</td>'
            f'<td>{values[f"team.{tid}.gpg"]}</td>'
            "</tr>"
        )
    r["table.career"] = "\n".join(rows)

    # Chart arrays used by the dashboard and the season chart
    def js_list(items):
        return "[" + ", ".join(str(x) for x in items) + "]"

    r["array.years"] = (
        "        const years = " + js_list([row["year"] for row in tables["years"]]) + ";\n"
        "        const goalsPerYear = " + js_list([row["goals"] for row in tables["years"]]) + ";\n"
        "        const cumulativeGoals = " + js_list([row["cumulative"] for row in tables["years"]]) + ";")
    r["array.years.labels"] = "                " + json.dumps(
        [row["year"] for row in tables["years"]])
    r["array.years.goals"] = "                " + json.dumps(
        [row["goals"] for row in tables["years"]])
    r["array.season.labels"] = "                " + json.dumps(
        [row["season"] for row in tables["season_chart"]])
    r["array.season.goals"] = "                " + json.dumps(
        [row["goals"] for row in tables["season_chart"]])
    r["array.body.all"] = "                " + json.dumps(
        [int(values[f"body.all.{s}"]) for s in BODY_SLOTS])
    for tid in data["bodyparts"]:
        r[f"array.body.{tid}"] = "                " + json.dumps(data["bodyparts"][tid])

    # ---- The dashboard's DATA object -------------------------------------
    # These are emitted rather than marked, because they are JavaScript object
    # literals with no element to hang an attribute on. The indentation matches
    # the page so the region can be diffed by eye.
    order = dashboard_order(data)
    career_comps = career_competitions(data)
    pad = max(len(tid) for tid in order) + 2       # widest "sporting:" style key

    def js_str(s):
        # match the page: single quotes normally, double when the label has one
        return f'"{s}"' if "'" in s else "'" + s + "'"

    def wrap(cells, indent, per_line):
        lines = []
        for i in range(0, len(cells), per_line):
            chunk = cells[i:i + per_line]
            last = i + per_line >= len(cells)
            lines.append(indent + ", ".join(chunk) + ("" if last else ","))
        return "\n".join(lines)

    def pairs_block(pairs, indent, per_line):
        return wrap([f"[{js_str(str(k))}, {v}]" for k, v in pairs], indent, per_line)

    def key(tid):
        return f"{tid + ':':{pad}}"

    rows = [f"                {key('all')}{{ name: 'All teams',   "
            f"games: {values['career.apps.raw']}, goals: {values['career.goals.raw']}, "
            f"assists: {values['career.assists.raw']} }},"]
    by_id = {t["id"]: t for t in data["teams"]}
    name_w = max(len(js_str(t["short"])) for t in data["teams"]) + 1
    # the numeric columns line up with the all row above them, which is widest
    apps_w = max([len(values["career.apps.raw"])]
                 + [len(values[f"team.{t}.apps"].replace(",", "")) for t in order]) + 1
    goals_w = max([len(values["career.goals.raw"])]
                  + [len(values[f"team.{t}.goals"].replace(",", "")) for t in order]) + 1
    for i, tid in enumerate(order):
        tail = "" if i == len(order) - 1 else ","
        rows.append(
            f"                {key(tid)}{{ name: {js_str(by_id[tid]['short']) + ',':{name_w}} "
            f"games: {values[f'team.{tid}.apps'].replace(',', '') + ',':{apps_w}} "
            f"goals: {values[f'team.{tid}.goals'].replace(',', '') + ',':{goals_w}} "
            f"assists: {values[f'team.{tid}.assists']} }}{tail}")
    r["array.dash.teams"] = "\n".join(rows)

    blocks = ["                all: [", pairs_block(career_comps.items(), " " * 20, 3),
              "                ],"]
    for i, tid in enumerate(order):
        tail = "" if i == len(order) - 1 else ","
        blocks += [f"                {tid}: [",
                   pairs_block(data["competitions"][tid].items(), " " * 20, 3),
                   f"                ]{tail}"]
    r["array.dash.competitions"] = "\n".join(blocks)

    finish = ["openplay", "penalties", "freekicks"]
    rows = [f"                {key('all')}"
            + json.dumps([int(values["career.openplay"].replace(",", "")),
                          int(values["penalties.total"].replace(",", "")),
                          int(values["freekicks.total"])]) + ","]
    for i, tid in enumerate(order):
        tail = "" if i == len(order) - 1 else ","
        rows.append(f"                {key(tid)}"
                    + json.dumps([int(values[f"{k}.{tid}"].replace(",", "")) for k in finish]) + tail)
    r["array.dash.finish"] = "\n".join(rows)

    rows = ["                labels: ['Right foot', 'Left foot', 'Headers', 'Other'],",
            f"                {key('all')}"
            + json.dumps([int(values[f"body.all.{s}"]) for s in BODY_SLOTS]) + ","]
    for i, tid in enumerate(order):
        tail = "" if i == len(order) - 1 else ","
        rows.append(f"                {key(tid)}{json.dumps(data['bodyparts'][tid])}{tail}")
    r["array.dash.bodypart"] = "\n".join(rows)

    rows = []
    club_ids = [tid for tid in order if tid != "portugal"]
    for i, tid in enumerate(club_ids):
        pairs = [(row["season"], sum(c["goals"] for c in row["comps"].values() if c))
                 for row in data["seasons"]
                 if row["team"] == tid and row.get("in_career", True)]
        tail = "" if i == len(club_ids) - 1 else ","
        rows.append(f"                {key(tid)}"
                    + "[" + ", ".join(f"['{s}', {g}]" for s, g in pairs) + f"]{tail}")
    r["array.dash.seasons"] = "\n".join(rows)

    r["array.dash.portugal_years"] = pairs_block(
        [(row["year"], row["goals"]) for row in tables["portugal_years"]], " " * 16, 6)

    # ---- The season chart's label axis -----------------------------------
    # The chart maps its series over this list, so a season missing here simply
    # has no column no matter what the data says. It was hand written and stopped
    # a season short, which is exactly how 2026/27 went unplotted.
    labels = sorted({row["season"] for row in data["seasons"]
                     if row.get("in_career", True)})
    # wrapped to the same line width the page already uses, so the block keeps
    # its shape as seasons are added
    cells = [f"'{label}'" for label in labels]
    lines, line = [], "        const allSeasonLabels = ["
    for i, cell in enumerate(cells):
        piece = cell + ("];" if i == len(cells) - 1 else ",")
        candidate = line + ("" if line.endswith("[") else " ") + piece
        if len(candidate) > 110 and not line.endswith("["):
            lines.append(line)
            line = " " * 12 + piece
        else:
            line = candidate
    lines.append(line)
    r["array.dash.season_labels"] = "\n".join(lines)

    # ---- The dashboard's opponent lists ----------------------------------
    # Left hand written at first, on the view that they were editorial. They are
    # not: a goal recorded against a named side moves them, so a hand written
    # list means the page under reports the opponent it was just told about.
    blocks = []
    groups = list(data.get("opponents", {}))
    for gi, group in enumerate(groups):
        goals = data["opponents"][group]
        apps = data.get("opponent_apps", {}).get(group, {})
        # sort by goals only: Python's sort is stable, so sides level on goals
        # keep the order the dataset holds, which is the order the page shows
        pairs = sorted(goals.items(), key=lambda kv: -kv[1])
        cells = [f"[{js_str(name)}, {n}, {apps.get(name, 0)}]" for name, n in pairs]
        blocks.append(f"                {group}: [")
        blocks.append(wrap(cells, " " * 20, 3))
        blocks.append("                ]" + ("" if gi == len(groups) - 1 else ","))
    r["array.dash.opponents"] = "\n".join(blocks)

    # ---- The home page sparkline ----------------------------------------
    # 25 bars with their geometry computed from the goals, plus the peak label
    # and the tick years. It was hand drawn, so the bars and their tooltips did
    # not move when a goal was scored and the chart contradicted its own label.
    rows = tables["years"]
    peak = max(r["goals"] for r in rows)
    scale = 140 / peak                      # the tallest bar is 140 units high
    def trim(x):
        return f"{x:.1f}".rstrip("0").rstrip(".")
    bars = []
    for i, row in enumerate(rows):
        h = row["goals"] * scale
        last = i == len(rows) - 1
        cls = "bar part" if last else ("bar peak" if row["goals"] == peak else "bar")
        noun = "goal" if row["goals"] == 1 else "goals"
        tail = " so far" if last else ""
        bars.append(
            f'                            <rect class="{cls}" x="{8 + 40 * i}" '
            f'y="{trim(168 - h)}" width="24" height="{trim(h)}" rx="4">'
            f'<title>{row["year"]}: {row["goals"]} {noun}{tail}</title></rect>')
    peak_i = next(i for i, r in enumerate(rows) if r["goals"] == peak)
    r["svg.spark"] = "\n".join(
        ['                            <line class="baseline" x1="0" y1="168.5" '
         'x2="1000" y2="168.5"></line>',
         f'                            <text class="peak-label" x="{8 + 40 * peak_i + 12}" '
         f'y="20">{peak}</text>']
        + bars
        + [f'                            <text class="tick" x="{8 + 40 * i + 12}" '
           f'y="188">{rows[i]["year"]}</text>'
           for i in range(0, len(rows), 4)])

    # ---- The dashboard's three share-of-career tables --------------------
    total = int(values["career.goals.raw"])

    def share_rows(pairs, indent):
        return "\n".join(
            f'{indent}<tr><th scope="row">{label}</th><td>{n}</td>'
            f'<td class="muted">{n / total * 100:.1f}%</td></tr>'
            for label, n in pairs)

    r["table.dash.competitions"] = share_rows(career_comps.items(), " " * 32)
    r["table.dash.finish"] = share_rows(
        [("Open play", int(values["career.openplay"].replace(",", ""))),
         ("Penalties", int(values["penalties.total"].replace(",", ""))),
         ("Free kicks", int(values["freekicks.total"]))], " " * 32)
    r["table.dash.bodypart"] = share_rows(
        [("Right foot", int(values["body.all.right"])),
         ("Left foot", int(values["body.all.left"])),
         ("Headers", int(values["body.all.head"])),
         ("Other", int(values["body.all.other"]))], " " * 32)

    return r


LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def check_pages():
    """A marker span inside a JSON-LD string breaks the structured data without
    changing a single visible pixel, so nothing else would catch it. Refuse to
    let that ship."""
    errors = []
    for name in PAGES:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for i, m in enumerate(LD_RE.finditer(text)):
            if "data-stat" in m.group(1):
                errors.append(f"{name}: JSON-LD block {i} contains a data-stat marker")
            try:
                json.loads(m.group(1))
            except ValueError as exc:
                errors.append(f"{name}: JSON-LD block {i} does not parse: {exc}")
    return errors


def write_html(data, values, regions, dry_run=False):
    report = {"values": 0, "attrs": 0, "regions": 0, "texts": 0,
              "missing": set(), "rules": [], "nested": [], "files": []}
    for name in PAGES:
        path = ROOT / name
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        updated = rewrite_page(original, values, regions, report)
        updated = apply_text_rules(updated, name, values, report)
        if updated != original:
            report["files"].append(name)
            if not dry_run:
                path.write_text(updated, encoding="utf-8")

    sitemap = update_sitemap(values, report, dry_run)
    if sitemap:
        report["files"].append(sitemap)
    return report


def update_sitemap(values, report, dry_run=False):
    """Every page the engine rebuilds genuinely changed, so its lastmod moves
    with the data. Pages the engine does not touch, such as the privacy policy,
    keep whatever date they already carry: claiming they changed would be a
    false signal to a crawler."""
    path = ROOT / "sitemap.xml"
    if not path.exists():
        return None
    original = path.read_text(encoding="utf-8")
    updated = original
    owned = {"index.html": "https://ronaldostats.app/"}
    owned.update({name: f"https://ronaldostats.app/{name}" for name in PAGES
                  if name != "index.html"})
    for name, loc in owned.items():
        pattern = (r"(<loc>" + re.escape(loc) + r"</loc>\s*<lastmod>)([^<]*)(</lastmod>)")
        hits = list(re.finditer(pattern, updated))
        if len(hits) != 1:
            report["rules"].append(
                f"sitemap.xml: expected 1 entry for {name}, found {len(hits)}")
            continue
        m = hits[0]
        updated = updated[:m.start(2)] + values["meta.updated.iso"] + updated[m.end(2):]
        report["texts"] += 1
    if updated == original:
        return None
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return "sitemap.xml"


# ----------------------------------------------------------------------------
# Events
# ----------------------------------------------------------------------------

def find_season_row(data, team, comp, season):
    season = season or data["meta"]["current_season"]
    for row in data["seasons"]:
        if row["team"] == team and row["season"] == season:
            if comp in row["comps"] and row["comps"][comp] is not None:
                return row
    return None


# The dashboard publishes opponents under group names of its own, not under the
# team id: Al Nassr's opponents live in "saudi" and Portugal's in "intl". Writing
# to the team id instead created a group nothing displayed, so the site quietly
# under reported the opponent it had just been told about.
OPPONENT_GROUP = {"alnassr": "saudi", "portugal": "intl", "sporting": "sporting",
                  "manutd": "manutd", "realmadrid": "realmadrid",
                  "juventus": "juventus"}
# Clubs also feed the combined all clubs list the dashboard shows by default.
OPPONENT_AGGREGATE = "club"


def record_opponent(data, team, opponent, new_appearance):
    """Add the goal, and the appearance, to every published list that already
    names this opponent. These lists are the top sides he has scored against
    rather than a complete record, so a name that is not on one is reported
    instead of being added: putting it there would silently reshape the chart."""
    groups = [OPPONENT_GROUP.get(team, team)]
    if team != "portugal":
        groups.append(OPPONENT_AGGREGATE)
    touched = []
    for group in groups:
        goals = data.setdefault("opponents", {}).setdefault(group, {})
        if opponent not in goals:
            continue
        goals[opponent] += 1
        touched.append(group)
        if new_appearance:
            apps = data.setdefault("opponent_apps", {}).setdefault(group, {})
            apps[opponent] = apps.get(opponent, 0) + 1
    if not touched:
        print(f"Note: {opponent} is not on any published opponent list, so no "
              f"opponent tally moved. Add it to data/ronaldo.json if it belongs.")
    return touched


def apply_goal(data, args):
    team = args.team
    year = args.year or dt.date.today().year
    comp = args.comp

    if team == "portugal":
        target = next((r for r in data["portugal_years"] if r["year"] == year), None)
        if target is None:
            target = {"year": year, "apps": 0, "goals": 0}
            data["portugal_years"].append(target)
        target["goals"] += 1
        if args.new_appearance:
            target["apps"] += 1
    else:
        row = find_season_row(data, team, comp, args.season)
        if row is None:
            sys.exit(
                f"No season row for team={team} season={args.season or data['meta']['current_season']} "
                f"comp={comp}. Add the row to data/ronaldo.json first, or pass --season.")
        row["comps"][comp]["goals"] += 1
        if args.new_appearance:
            row["comps"][comp]["apps"] += 1

    # Calendar year
    yr = next((r for r in data["years"] if r["year"] == year), None)
    if yr is None:
        born = dt.date.fromisoformat(data["meta"]["born"])
        yr = {"year": year, "goals": 0, "age": year - born.year}
        data["years"].append(yr)
    yr["goals"] += 1

    # Competition tally, recorded against the team so both charts move together
    label = args.competition_label or comp
    block = data["competitions"].setdefault(team, {})
    block[label] = block.get(label, 0) + 1

    # Body part
    slot = BODY_SLOTS.index(args.body)
    data["bodyparts"].setdefault(team, [0, 0, 0, 0])[slot] += 1

    # Finish type
    if args.type == "penalty":
        data["penalties"][team] = data["penalties"].get(team, 0) + 1
    elif args.type == "freekick":
        data["freekicks"][team] = data["freekicks"].get(team, 0) + 1

    # Opponent
    if args.opponent:
        record_opponent(data, team, args.opponent, args.new_appearance)

    # Assists created in the same match
    if args.assists:
        t = next(t for t in data["teams"] if t["id"] == team)
        t["assists"] += args.assists

    data.setdefault("log", []).append({
        "date": dt.date.today().isoformat(),
        "event": "goal", "team": team, "comp": comp, "year": year,
        "body": args.body, "type": args.type, "opponent": args.opponent,
        "assists": args.assists, "new_appearance": args.new_appearance,
    })
    return data


def apply_appearance(data, args):
    if args.team == "portugal":
        year = args.year or dt.date.today().year
        target = next((r for r in data["portugal_years"] if r["year"] == year), None)
        if target is None:
            target = {"year": year, "apps": 0, "goals": 0}
            data["portugal_years"].append(target)
        target["apps"] += 1
    else:
        row = find_season_row(data, args.team, args.comp, args.season)
        if row is None:
            sys.exit("No matching season row. Check the team, season and competition.")
        row["comps"][args.comp]["apps"] += 1
    data.setdefault("log", []).append({
        "date": dt.date.today().isoformat(), "event": "appearance",
        "team": args.team, "comp": args.comp})
    return data


def apply_assist(data, args):
    t = next((t for t in data["teams"] if t["id"] == args.team), None)
    if t is None:
        sys.exit(f"Unknown team {args.team}")
    t["assists"] += args.count
    data.setdefault("log", []).append({
        "date": dt.date.today().isoformat(), "event": "assist",
        "team": args.team, "count": args.count})
    return data


def apply_hattrick(data, args):
    data["hattricks"][args.team] = data["hattricks"].get(args.team, 0) + 1
    data.setdefault("log", []).append({
        "date": dt.date.today().isoformat(), "event": "hattrick", "team": args.team})
    return data


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Update ronaldostats.app statistics.")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("goal", help="record one goal")
    g.add_argument("--team", required=True,
                   help="sporting, manutd, realmadrid, juventus, alnassr, portugal")
    g.add_argument("--comp", required=True,
                   help="season row competition slot: league, cup, lcup, cont, other")
    g.add_argument("--competition-label", dest="competition_label",
                   help="display name for the competitions chart, e.g. Saudi Pro League")
    g.add_argument("--season", help="defaults to meta.current_season")
    g.add_argument("--year", type=int, help="calendar year, defaults to today")
    g.add_argument("--body", default="right", choices=BODY_SLOTS)
    g.add_argument("--type", default="openplay",
                   choices=["openplay", "penalty", "freekick"])
    g.add_argument("--opponent")
    g.add_argument("--assists", type=int, default=0)
    g.add_argument("--new-appearance", dest="new_appearance", action="store_true",
                   help="also add one appearance for this match")

    a = sub.add_parser("appearance", help="record one appearance with no goal")
    a.add_argument("--team", required=True)
    a.add_argument("--comp", default="league")
    a.add_argument("--season")
    a.add_argument("--year", type=int)

    s = sub.add_parser("assist", help="record assists")
    s.add_argument("--team", required=True)
    s.add_argument("--count", type=int, default=1)

    h = sub.add_parser("hattrick", help="record a hat trick")
    h.add_argument("--team", required=True)

    sub.add_parser("build", help="rewrite the HTML from the current data")
    sub.add_parser("show", help="print the current headline figures")
    sub.add_parser("undo", help="restore the dataset from the last backup")
    sub.add_parser("check", help="validate without writing anything")

    args = p.parse_args()

    if args.cmd == "undo":
        if not BACKUP.exists():
            sys.exit("No backup to restore.")
        shutil.copy(BACKUP, DATA)
        data = load()
        values, tables, facts = derive(data)
        regions = build_regions(data, tables, values)
        write_html(data, values, regions)
        print("Reverted to the previous dataset and rebuilt the pages.")
        return

    data = load()

    if args.cmd in ("goal", "appearance", "assist", "hattrick"):
        shutil.copy(DATA, BACKUP)
        handlers = {"goal": apply_goal, "appearance": apply_appearance,
                    "assist": apply_assist, "hattrick": apply_hattrick}
        data = handlers[args.cmd](copy.deepcopy(data), args)

    values, tables, facts = derive(data)
    errors = validate(data, facts)

    if errors:
        print("VALIDATION FAILED, nothing was written:")
        for e in errors:
            print("  " + e)
        sys.exit(1)

    if args.cmd == "check":
        page_errors = check_pages()
        if page_errors:
            print("PAGE CHECK FAILED:")
            for e in page_errors:
                print("  " + e)
            sys.exit(1)
        print("All totals reconcile, and every page's JSON-LD still parses.")
        return

    if args.cmd == "show":
        print(f"Goals      {values['career.goals']}")
        print(f"Apps       {values['career.apps']}")
        print(f"Assists    {values['career.assists']}")
        print(f"Per game   {values['career.gpg']}")
        print(f"To 1,000   {values['career.remaining']}")
        print(f"Updated    {values['meta.updated.long']}")
        return

    if args.cmd != "build":
        save(data)
        values, tables, facts = derive(data)

    regions = build_regions(data, tables, values)
    report = write_html(data, values, regions)

    print(f"Goals now {values['career.goals']}, {values['career.remaining']} from 1,000.")
    print(f"Rewrote {report['values']} values, {report['attrs']} attributes, "
          f"{report['regions']} table regions and {report['texts']} text rules "
          f"in {len(report['files'])} files: {', '.join(report['files']) or 'none'}")
    if report["nested"]:
        print("Markers nested inside another marker, which would erase them:")
        for line in sorted(set(report["nested"])):
            print("  " + line)
    if report["rules"]:
        print("Text rules that did not match exactly once:")
        for line in report["rules"]:
            print("  " + line)
    if report["missing"]:
        print("Markers with no matching data key (check the migration):")
        for key in sorted(report["missing"]):
            print("  " + key)


if __name__ == "__main__":
    main()
