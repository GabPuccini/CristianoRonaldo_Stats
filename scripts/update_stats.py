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
    out["career.assists"] = f"{career_assists:,}"
    out["career.gpg"] = f"{career_goals / career_apps:.2f}"
    out["career.remaining"] = str(remaining)
    out["career.pct"] = f"{pct:.1f}"
    out["career.target"] = f"{target:,}"
    out["career.progress_label"] = f"{career_goals:,} / {target:,}"
    out["career.fillstyle"] = f"width: {pct:.1f}%;"
    out["career.club_goals"] = f"{sum(v for k, v in club_goals.items() if k != 'portugal'):,}"

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
        for tid, n in block.items():
            out[f"{group}.{tid}"] = f"{n:,}"

    # Body parts, career and per team
    totals = [0, 0, 0, 0]
    for tid, slots in data["bodyparts"].items():
        for i, n in enumerate(slots):
            totals[i] += n
        for i, slot in enumerate(BODY_SLOTS):
            out[f"body.{tid}.{slot}"] = str(slots[i])
    for i, slot in enumerate(BODY_SLOTS):
        out[f"body.all.{slot}"] = str(totals[i])

    # Competitions
    for name, n in data["competitions"].items():
        out[f"comp.{slug(name)}"] = str(n)

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

    # Dates
    updated = dt.date.fromisoformat(data["meta"]["updated"])
    out["meta.updated.iso"] = updated.isoformat()
    out["meta.updated.long"] = f"{updated.day} {updated:%B %Y}"
    out["meta.updated.short"] = f"{updated:%B %Y}"

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

    comp_sum = sum(data["competitions"].values())
    if comp_sum != cg:
        errors.append(f"competitions sum to {comp_sum}, career goals are {cg}")

    for tid, slots in data["bodyparts"].items():
        team_goals = facts["club_goals"].get(tid, 0)
        if sum(slots) != team_goals:
            errors.append(
                f"body parts for {tid} sum to {sum(slots)}, that team has {team_goals} goals")

    pens = sum(data["penalties"].values())
    fks = sum(data["freekicks"].values())
    if pens + fks > cg:
        errors.append(f"penalties plus free kicks ({pens + fks}) exceed career goals ({cg})")

    for tid in data["penalties"]:
        team_goals = facts["club_goals"].get(tid, 0)
        combined = data["penalties"].get(tid, 0) + data["freekicks"].get(tid, 0)
        if combined > team_goals:
            errors.append(f"set pieces for {tid} ({combined}) exceed that team's {team_goals} goals")

    for name, block in data.get("opponents", {}).items():
        total = sum(block.values())
        team_goals = facts["club_goals"].get(name, 0)
        if team_goals and total > team_goals:
            errors.append(f"opponent goals for {name} sum to {total}, above that team's {team_goals}")

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
REGION_RE = re.compile(
    r"(?P<open><!--\s*STATS:BEGIN\s+(?P<key>[\w.]+)\s*-->)"
    r"(?P<body>.*?)"
    r"(?P<close><!--\s*STATS:END\s+(?P=key)\s*-->)",
    re.DOTALL,
)
ATTR_SPEC_RE = re.compile(r'data-stat-attr="([^"]+)"')


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
        body = values[key] if key is not None else m.group("body")
        if key is not None:
            report["values"] += 1
        return f'<{m.group("tag")}{attrs}>{body}</{m.group("tag")}>'

    def region_sub(m):
        key = m.group("key")
        if key not in regions:
            report["missing"].add("region:" + key)
            return m.group(0)
        report["regions"] += 1
        return f'{m.group("open")}\n{regions[key]}\n{m.group("close")}'

    text = VALUE_RE.sub(value_sub, text)
    text = REGION_RE.sub(region_sub, text)
    return text


def build_regions(data, tables, values):
    teams = {t["id"]: t for t in data["teams"]}
    r = {}

    # Calendar year table body
    rows = []
    for row in tables["years"]:
        rows.append(
            "                            <tr>"
            f'<th scope="row">{row["year"]}</th>'
            f'<td>{row["goals"]}</td>'
            f'<td>{row["cumulative"]:,}</td>'
            f'<td>{row["age"]}</td>'
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

    return r


def write_html(data, values, regions, dry_run=False):
    report = {"values": 0, "attrs": 0, "regions": 0, "missing": set(), "files": []}
    for name in PAGES:
        path = ROOT / name
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        updated = rewrite_page(original, values, regions, report)
        if updated != original:
            report["files"].append(name)
            if not dry_run:
                path.write_text(updated, encoding="utf-8")
    return report


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

    # Competition tally
    label = args.competition_label or comp
    data["competitions"][label] = data["competitions"].get(label, 0) + 1

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
        block = data.setdefault("opponents", {}).setdefault(team, {})
        block[args.opponent] = block.get(args.opponent, 0) + 1

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
        print("All totals reconcile.")
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
    print(f"Rewrote {report['values']} values, {report['attrs']} attributes and "
          f"{report['regions']} table regions in {len(report['files'])} files: "
          f"{', '.join(report['files']) or 'none'}")
    if report["missing"]:
        print("Markers with no matching data key (check the migration):")
        for key in sorted(report["missing"]):
            print("  " + key)


if __name__ == "__main__":
    main()
