"""
The Messi vs Ronaldo page, messi-vs-ronaldo.html.

Every comparison on that page is written here from the dataset: Ronaldo's side
from the same derived values as the home page, Messi's from the messi block in
data/ronaldo.json, and their meetings from versus. Which of the two leads a
row, and so which cell is highlighted and who each answer names first, is
worked out on every build, so a figure that overtakes the other changes the
page without anyone editing it. The prose with no live figure in it, the
context notes and the sources, stays hand written in the page.

Record a Messi match with the engine's messi command:
    python scripts/update_stats.py messi --goals 2 --assists 1
"""

import datetime as dt
import html as htmllib
import sys

PAGE = "messi-vs-ronaldo.html"

NAME = {"r": "Cristiano Ronaldo", "m": "Lionel Messi"}
SHORT = {"r": "Ronaldo", "m": "Messi"}
OTHER = {"r": "m", "m": "r"}

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
         8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}

# The trophy table counts each honour in one row. Messi's honours carry their
# kind in the dataset; Ronaldo's are the home page's lists, so they are sorted
# by name here, and anything not named counts only in the totals.
RONALDO_KINDS = {
    "Premier League": "league", "La Liga": "league", "Serie A": "league", "Saudi Pro League": "league",
    "UEFA Champions League": "championsleague", "FIFA Club World Cup": "clubworldcup",
    "UEFA Super Cup": "uefasupercup",
    "FA Cup": "cup", "Football League Cup": "cup", "Copa del Rey": "cup", "Coppa Italia": "cup",
    "Supertaça Cândido de Oliveira": "supercup", "FA Community Shield": "supercup",
    "Supercopa de España": "supercup", "Supercoppa Italiana": "supercup",
    "FIFA World Cup": "worldcup", "UEFA European Championship": "continental",
}
KINDS = {"league", "championsleague", "clubworldcup", "uefasupercup", "cup", "supercup",
         "worldcup", "continental", "other"}

# Ronaldo's clubs in the order the page lists them, with Portugal last
RONALDO_TEAMS = [("sporting", "Sporting CP"), ("manutd", "Manchester United"),
                 ("realmadrid", "Real Madrid"), ("juventus", "Juventus"),
                 ("alnassr", "Al Nassr"), ("portugal", "Portugal")]

# The awards Ronaldo has won as his league's top scorer, by the slug the engine
# gives each individual honour
RONALDO_LEAGUE_TOP = ["premierleaguegoldenboot", "pichichitrophy", "capocannoniere",
                      "saudiproleaguegoldenboot"]


def _n(values, key):
    return int(str(values[key]).replace(",", ""))


def _slug(name):
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _age(born, on):
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def _long(d):
    return f"{d.day} {d:%B %Y}"


def page_date(data):
    """The page moves when either side does, so it is dated by the later."""
    return max(dt.date.fromisoformat(data["meta"]["updated"]),
               dt.date.fromisoformat(data["messi"]["updated"]))


def dates(data):
    """Values the engine merges into its own: the dates the head and the sitemap
    need. They are not numbers, so they never enter the coverage scan."""
    if "messi" not in data:
        return {}
    d = page_date(data)
    m = dt.date.fromisoformat(data["messi"]["updated"])
    return {"mvr.updated.iso": d.isoformat(), "mvr.updated.long": _long(d),
            "messi.updated.long": _long(m)}


def trophy_counts(groups):
    """groups: (national, [{name, kind, years}]) for each team."""
    c = {k: 0 for k in KINDS}
    c.update(total=0, club=0, national=0)
    for national, items in groups:
        for t in items:
            n = len(t["years"])
            c[t["kind"]] += n
            c["total"] += n
            c["national" if national else "club"] += n
    return c


def ronaldo_trophies(data):
    groups = []
    for tid, _ in RONALDO_TEAMS:
        items = [dict(t, kind=RONALDO_KINDS.get(t["name"], "other"))
                 for t in data["honours"]["teams"].get(tid, [])]
        groups.append((tid == "portugal", items))
    return groups


def messi_trophies(data):
    national = {t["id"]: t.get("national", False) for t in data["messi"]["teams"]}
    return [(national[g["team"]], g["items"]) for g in data["messi"]["trophies"]]


def ronaldo(data, values):
    v = lambda k: _n(values, k)
    vs = data["versus"]["ronaldo"]
    seasons = [r for r in data["seasons"] if r.get("in_career", True)]

    def best(slot, rows):
        rows = [r for r in rows if r["comps"].get(slot)]
        top = max(rows, key=lambda r: r["comps"][slot]["goals"])
        return top["comps"][slot]["goals"], top["season"]

    # the AFC Champions League sits in the same slot, so Al Nassr is left out
    cl_goals, cl_season = best("cont", [r for r in seasons if r["team"] not in ("alnassr", "portugal")])
    league_goals, league_season = best("league", [r for r in seasons if r["team"] != "portugal"])
    big3 = [r for r in seasons if r["team"] in ("manutd", "realmadrid", "juventus")
            and r["comps"].get("league") and r["comps"]["league"]["apps"]]
    awards = {_slug(a["name"]): a for a in data["honours"]["individual"]}
    bd = data["ballon_dor"]
    R = dict(
        apps=v("career.apps"), goals=v("career.goals"), assists=v("career.assists"),
        club_apps=v("career.club_apps"), club_goals=v("career.club_goals"),
        intl_apps=v("team.portugal.apps"), intl_goals=v("team.portugal.goals"),
        hattricks=v("hattricks.total"), intl_hattricks=v("hattricks.portugal"),
        pens=v("penalties.total"), freekicks=v("freekicks.total"), headers=v("body.all.head"),
        laliga=v("comp.laliga"), cl=v("comp.championsleague"), cdr=v("comp.copadelrey"),
        wc=v("comp.worldcup"), continental=v("comp.euros"),
        bdo=sum(1 for r in bd if r.get("position") == 1),
        bdo_second=sum(1 for r in bd if r.get("position") == 2),
        bdo_third=sum(1 for r in bd if r.get("position") == 3),
        bdo_noms=len(bd),
        bdo_years=[str(r["year"]) for r in bd if r.get("position") == 1],
        best=v("award.thebestfifamensplayer"), worldplayer=v("award.fifaworldplayeroftheyear"),
        goldenshoe=v("award.europeangoldenshoe"), uefa_player=v("award.uefamensplayeroftheyear"),
        uefa_club=v("award.uefaclubfootballeroftheyear"), cl_top=v("award.uefachampionsleaguetopscorer"),
        puskas=v("award.fifapuskasaward"), cwc_ball=v("award.fifaclubworldcupgoldenball"),
        continental_top=v("award.uefaeuropeanchampionshipgoldenboot"),
        wc_ball=vs["international"]["worldcup_goldenball"],
        league_top=[(awards[s]["name"], awards[s]["count"]) for s in RONALDO_LEAGUE_TOP
                    if s in awards and awards[s]["count"]],
        best_season=v("season.best.goals"), best_season_name=values["season.best.season"],
        best_league=league_goals, best_league_name=league_season,
        best_year=v("year.best.goals"), best_year_name=values["year.best.year"],
        cl_best=cl_goals, cl_best_name=cl_season,
        big3_seasons=len({r["season"] for r in big3}),
        big3_span=f"{min(r['season'] for r in big3)} to {max(r['season'] for r in big3)}",
        big3_goals=v("comp.laliga") + v("comp.premierleague") + v("comp.seriea"),
        born=dt.date.fromisoformat(data["meta"]["born"]),
        profile=vs["profile"], intl=vs["international"],
        last_european=vs["last_european_match"],
        teams=[(name, values[f"team.{k}.years"], v(f"team.{k}.apps"), v(f"team.{k}.goals"))
               for k, name in RONALDO_TEAMS],
        seasons=[(r["season"], dict(RONALDO_TEAMS)[r["team"]],
                  sum(c["apps"] for c in r["comps"].values() if c),
                  sum(c["goals"] for c in r["comps"].values() if c))
                 for r in seasons if r["team"] != "portugal"],
        trophy_groups=ronaldo_trophies(data),
        rm_apps=v("team.realmadrid.apps"), rm_goals=v("team.realmadrid.goals"),
        nl_goals=v("comp.portugal.nationsleague"),
        cl_assists=vs["championsleague_assists"],
        pens_missed=data["penalties_missed"],
        # the countries where he has won a title with his club, in the order he
        # played there, and whether that is every club he has played for
        title_countries=[data["transfer_clubs"][tid]["country"]
                         for (tid, _), (_, items) in zip(RONALDO_TEAMS, ronaldo_trophies(data))
                         if tid in data["transfer_clubs"] and items],
        titles_everywhere=all(data["honours"]["teams"].get(tid) for tid in data["transfer_clubs"]),
        nl_titles=sum(len(t["years"]) for t in data["honours"]["teams"].get("portugal", [])
                      if t["name"] == "UEFA Nations League"),
    )
    R["league_top_count"] = sum(c for _, c in R["league_top"])
    R["trophies"] = trophy_counts(R["trophy_groups"])
    return R


def messi(data):
    m = data["messi"]
    teams = m["teams"]
    club = [t for t in teams if not t.get("national")]
    nat = [t for t in teams if t.get("national")]
    names = {t["id"]: t["name"] for t in teams}
    year = dt.date.fromisoformat(m["updated"]).year
    aw = m["awards"]
    M = dict(
        apps=sum(t["apps"] for t in teams), goals=sum(t["goals"] for t in teams),
        assists=m["career"]["assists"],
        club_apps=sum(t["apps"] for t in club), club_goals=sum(t["goals"] for t in club),
        intl_apps=sum(t["apps"] for t in nat), intl_goals=sum(t["goals"] for t in nat),
        hattricks=sum(t["hattricks"] for t in teams), intl_hattricks=sum(t["hattricks"] for t in nat),
        pens=m["career"]["penalties"], freekicks=m["career"]["freekicks"], headers=m["career"]["headers"],
        pens_missed=m["career"]["penalties_missed"],
        laliga=m["competitions"]["laliga"], cl=m["competitions"]["championsleague"],
        cl_assists=m["competitions"]["championsleague_assists"],
        cdr=m["competitions"]["copadelrey"], wc=m["competitions"]["worldcup"],
        continental=m["competitions"]["continental"],
        bdo=len(aw["ballondor"]), bdo_second=aw["ballondor_second"], bdo_third=aw["ballondor_third"],
        bdo_noms=data["ballon_dor_next_most"]["nominations"], bdo_years=aw["ballondor"],
        best=aw["thebest"], worldplayer=aw["worldplayer"], goldenshoe=aw["goldenshoe"],
        uefa_player=aw["uefa_player"], uefa_club=aw["uefa_club"], cl_top=aw["cl_topscorer"],
        puskas=aw["puskas"], cwc_ball=aw["clubworldcup_goldenball"],
        continental_top=aw["continental_topscorer"], wc_ball=aw["worldcup_goldenball"],
        league_top=[(a["name"], len(a["years"])) for a in aw["league_topscorer"]],
        best_season=m["best"]["season_goals"], best_season_name=m["best"]["season"],
        best_league=m["best"]["league_goals"], best_league_name=m["best"]["league_season"],
        best_year=m["best"]["year_goals"], best_year_name=m["best"]["year"],
        cl_best=m["best"]["cl_goals"], cl_best_name=m["best"]["cl_season"],
        big3_seasons=m["top_leagues"]["seasons"], big3_span=m["top_leagues"]["span"],
        big3_goals=m["competitions"]["laliga"],
        born=dt.date.fromisoformat(m["born"]),
        profile=m["profile"], intl=m["international"],
        last_european=m["top_leagues"]["last_european_match"],
        teams=[(t["name"], t["years"], t["apps"], t["goals"]) for t in teams],
        seasons=[(r.get("season") or f"{r['from']} to {year}", names[r["team"]], r["apps"], r["goals"])
                 for r in m["seasons"]],
        trophy_groups=messi_trophies(data),
        names=names,
    )
    M["league_top_count"] = sum(c for _, c in M["league_top"])
    M["trophies"] = trophy_counts(M["trophy_groups"])
    return M


# ----------------------------------------------------------------------------
# Markup
# ----------------------------------------------------------------------------

def fmt(x):
    if isinstance(x, float):
        return f"{x:.2f}"
    if isinstance(x, int):
        return f"{x:,}"
    return x


def gpg(goals, games):
    return goals / games if games else 0.0


def leader(r, m):
    """'r', 'm', or None for level."""
    return "r" if r > m else "m" if m > r else None


def lead_cells(r, m, mode="hi"):
    if not mode or not isinstance(r, (int, float)) or not isinstance(m, (int, float)):
        return "", ""
    # compare what the reader sees, so two averages printed alike are level
    if isinstance(r, float) or isinstance(m, float):
        r, m = round(r, 2), round(m, 2)
    who = leader(r, m) if mode == "hi" else leader(m, r)
    lead = ' class="lead"'
    return (lead, "") if who == "r" else ("", lead) if who == "m" else ("", "")


CMP_HEAD = ('<thead><tr><th scope="col">Cristiano Ronaldo</th><th scope="col"><span class="sr">Statistic</span>'
            '</th><th scope="col">Lionel Messi</th></tr></thead>')


def cmp_table(rows, caption):
    """rows: (label, ronaldo, messi, mode). mode 'hi' highlights the larger and
    None neither, for rows that are not a contest."""
    out = ['<div class="tbl"><table class="cmp">', f'<caption class="sr">{caption}</caption>', CMP_HEAD, "<tbody>"]
    for label, r, m, mode in rows:
        rc, mc = lead_cells(r, m, mode)
        out.append(f'<tr><td{rc}>{fmt(r)}</td><th scope="row">{label}</th><td{mc}>{fmt(m)}</td></tr>')
    out.append("</tbody></table></div>")
    return out


def note(text):
    return [f'<p class="note">{text}</p>']


def sub(title):
    return [f'<h3 class="sub">{title}</h3>']


def two(left, right):
    return (['<div class="two">', "<div>"] + left + ["</div>", "<div>"] + right + ["</div>", "</div>"])


def series(items):
    items = list(items)
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def word(n):
    return WORDS.get(n, f"{n:,}")


def profile(P, who, born, age):
    p = P["profile"]
    rows = [("Born", f"{born.day} {born:%B %Y} ({age})"), ("Place of birth", p["birthplace"]),
            ("Height", p["height"]), ("Foot", p["foot"]), ("Position", p["position"]),
            ("Current club", p["club"]), ("Senior debut", p["debut"])]
    trs = "".join(f'<tr><th scope="row">{k}</th><td>{htmllib.escape(v, quote=False)}</td></tr>' for k, v in rows)
    return [f'<div class="profile"><div class="ph"><span class="num">#{p["number"]}</span>'
            f'<span class="pname">{NAME[who]}</span></div>',
            f'<p class="full">{p["full_name"]}</p><table class="facts">{trs}</table></div>']


def club_table(rows, who):
    out = ['<div class="tbl"><table class="list">', f'<caption class="sr">{who} by team</caption>',
           '<thead><tr><th scope="col">Team</th><th scope="col">Games</th><th scope="col">Goals</th>'
           '</tr></thead>', "<tbody>"]
    for name, years, a, g in rows:
        out.append(f'<tr><th scope="row">{name}<span class="yrs">{years}</span></th>'
                   f'<td>{a:,}</td><td>{g:,}</td></tr>')
    out.append("</tbody></table></div>")
    return out


def season_table(rows, who):
    out = ['<div class="tbl"><table class="list seasons">', f'<caption class="sr">{who} club goals by season</caption>',
           '<thead><tr><th scope="col">Season</th><th scope="col">Club</th><th scope="col">Games</th>'
           '<th scope="col">Goals</th></tr></thead>', "<tbody>"]
    for s, club, a, g in rows:
        out.append(f'<tr><th scope="row">{s}</th><td class="club">{club}</td><td>{a}</td><td>{g}</td></tr>')
    out.append("</tbody>")
    out.append(f'<tfoot><tr><th scope="row">Total</th><td></td><td>{sum(r[2] for r in rows):,}</td>'
               f'<td>{sum(r[3] for r in rows):,}</td></tr></tfoot></table></div>')
    return out


def trophy_list(title, total, blocks):
    out = [f'<h3 class="sub big">{title} <span class="cnt">{total}</span></h3>']
    for team, items in blocks:
        out.append(f'<h3 class="sub">{team}</h3>')
        out.append('<ul class="trophies">' + "".join(
            f'<li><span class="t">{htmllib.escape(t["name"], quote=False)}</span><span class="n">{len(t["years"])}</span>'
            f'<span class="y">{", ".join(t["years"])}</span></li>' for t in items) + "</ul>")
    return out


def award_phrase(name, count):
    if count == 1:
        return f"the {name}"
    plural = name[:-1] + "ies" if name.endswith("y") else name + "s"
    return f"{word(count)} {plural}"


# ----------------------------------------------------------------------------
# Questions
# ----------------------------------------------------------------------------

def questions(data, R, M):
    P = {"r": R, "m": M}
    h2h = data["versus"]["head_to_head"]
    cl = data["versus"]["clasico"]
    T = {k: P[k]["trophies"] for k in P}
    G = {k: gpg(P[k]["goals"], P[k]["apps"]) for k in P}
    qs = []

    def most(key, lead_text, other_text, level_text):
        """The usual answer shape: the leader first, then the other."""
        x = {k: P[k][key] for k in P} if isinstance(key, str) else key
        w = leader(x["r"], x["m"])
        if w is None:
            return level_text(x["r"])
        return lead_text(w, x) + " " + other_text(OTHER[w], x)

    qs.append(("Who has more goals, Messi or Ronaldo?", most(
        "goals",
        lambda w, x: f"{NAME[w]}, with {x[w]:,} goals in {P[w]['apps']:,} games.",
        lambda o, x: f"{NAME[o]} has {x[o]:,} goals in {P[o]['apps']:,} games.",
        lambda n: f"They are level on {n:,} goals.")))

    w = leader(round(G["r"], 2), round(G["m"], 2))
    a = (f"{SHORT[w]}, with {G[w]:.2f} goals per game. {SHORT[OTHER[w]]} averages {G[OTHER[w]]:.2f}."
         if w else f"They are level, at {G['r']:.2f} goals per game each.")
    # Ronaldo was a winger until he joined Real Madrid, which the career
    # average hides, so the answer gives the two spells apart
    rows = [r for r in data["seasons"] if r.get("in_career", True)]
    madrid = min(r["season"] for r in rows if r["team"] == "realmadrid")
    early = [r for r in rows if r["season"] < madrid]
    spells = {t: len({r["season"] for r in early if r["team"] == t}) for t in ("sporting", "manutd")}
    total = lambda k: sum(c[k] for r in early for c in r["comps"].values() if c)
    a += (f" Ronaldo played mainly as a winger in his first {word(sum(spells.values()))} senior seasons, "
          f"{word(spells['sporting'])} with Sporting CP and {word(spells['manutd'])} with Manchester United in "
          f"the Premier League, which was first in UEFA's league rankings in 2008 and 2009. He scored "
          f"{total('goals')} goals in {total('apps')} club games in those seasons. He played as a forward from "
          f"his move to Real Madrid in {madrid[:4]} and scored {R['rm_goals']:,} goals in "
          f"{R['rm_apps']:,} games for them.")
    qs.append(("Who has the better goals per game record?", a))

    qs.append(("Who has more assists?", most(
        "assists",
        lambda w, x: f"{SHORT[w]}, with {x[w]:,} assists.",
        lambda o, x: f"{SHORT[o]} has {x[o]:,}.",
        lambda n: f"They are level on {n:,} assists.")))

    a = most("bdo", lambda w, x: f"{SHORT[w]} has won {x[w]} and {SHORT[OTHER[w]]} {x[OTHER[w]]}.",
             lambda o, x: "", lambda n: f"Both have won {n}.").strip()
    nw = leader(R["bdo_noms"], M["bdo_noms"])
    a += (f" {SHORT[nw]} has been shortlisted {P[nw]['bdo_noms']} times and {SHORT[OTHER[nw]]} "
          f"{P[OTHER[nw]]['bdo_noms']}." if nw else f" Both have been shortlisted {R['bdo_noms']} times.")
    qs.append(("Who has more Ballon d'Or awards?", a))

    qs.append(("Who has won more trophies?", most(
        {k: T[k]["total"] for k in P},
        lambda w, x: f"{SHORT[w]}, with {x[w]} senior team trophies.",
        lambda o, x: f"{SHORT[o]} has {x[o]}.",
        lambda n: f"Both have {n} senior team trophies.")))

    tw = leader(T["r"]["championsleague"], T["m"]["championsleague"])
    gw = leader(R["cl"], M["cl"])
    if tw and tw == gw:
        o = OTHER[tw]
        a = (f"{SHORT[tw]}, with {T[tw]['championsleague']} UEFA Champions League titles and {P[tw]['cl']} goals. "
             f"{SHORT[o]} has {T[o]['championsleague']} titles and {P[o]['cl']} goals.")
    else:
        a = (f"Ronaldo has {T['r']['championsleague']} UEFA Champions League titles and {R['cl']} goals. "
             f"Messi has {T['m']['championsleague']} titles and {M['cl']} goals.")
    a += (" Messi was injured and did not play in the 2006 final, which Barcelona won against Arsenal, "
          "but he was counted as a winner.")
    qs.append(("Who has more Champions League titles and goals?", a))

    qs.append(("Who has more assists in the Champions League?", most(
        "cl_assists",
        lambda w, x: f"{SHORT[w]}, with {x[w]} UEFA Champions League assists.",
        lambda o, x: f"{SHORT[o]} has {x[o]}.",
        lambda n: f"They are level on {n} UEFA Champions League assists.")))

    caps = {"r": f"{R['intl_goals']} goals in {R['intl_apps']} caps for Portugal",
            "m": f"{M['intl_goals']} goals in {M['intl_apps']} caps for Argentina"}
    after = {"r": "", "m": f" before retiring from international football on {M['intl']['retired']}"}
    w = leader(R["intl_goals"], M["intl_goals"]) or "r"
    o = OTHER[w]
    qs.append(("Who has more international goals?",
               f"{SHORT[w]}, with {caps[w]}{after[w]}. {SHORT[o]} scored {caps[o]}{after[o]}."))

    wt = {"r": T["r"]["worldcup"], "m": T["m"]["worldcup"]}
    a = ("No. " if not wt["r"] else f"Yes, {wt['r']} times. ") + (
        "Messi won the 2022 FIFA World Cup with Argentina, and lost the 2014 final to Germany and the "
        "2026 final to Spain.")
    qs.append(("Has Ronaldo won the World Cup?", a))

    qs.append(("How many penalties did Argentina get at the 2022 World Cup?",
               "Five, all taken by Messi. He scored against Saudi Arabia, the Netherlands, Croatia and France, "
               "and Wojciech Szczesny saved his penalty against Poland. Four of his seven goals at the 2022 "
               "FIFA World Cup were penalties."))

    hw = leader(h2h["ronaldo"]["wins"], h2h["messi"]["wins"])
    hk = {"r": "ronaldo", "m": "messi"}
    if hw:
        wins = (f"{SHORT[hw]} has won {h2h[hk[hw]]['wins']}, {SHORT[OTHER[hw]]} {h2h[hk[OTHER[hw]]]['wins']}, "
                f"and {h2h['draws']} ended level.")
    else:
        wins = f"They have won {h2h['messi']['wins']} each, and {h2h['draws']} ended level."
    gw = leader(h2h["ronaldo"]["goals"], h2h["messi"]["goals"]) or "m"
    qs.append(("What is the head to head record between Messi and Ronaldo?",
               f"They have met {h2h['matches']} times. {wins} {SHORT[gw]} scored {h2h[hk[gw]]['goals']} goals "
               f"in those games and {SHORT[OTHER[gw]]} {h2h[hk[OTHER[gw]]]['goals']}."))

    against = {"r": "against Barcelona", "m": "against Real Madrid"}
    gw = leader(cl["ronaldo"]["goals"], cl["messi"]["goals"]) or "m"
    o = OTHER[gw]
    qs.append(("Who scored more goals in El Clasico?",
               f"{SHORT[gw]}, with {cl[hk[gw]]['goals']} goals in {cl[hk[gw]]['matches']} matches {against[gw]}. "
               f"{SHORT[o]} scored {cl[hk[o]]['goals']} in {cl[hk[o]]['matches']} matches {against[o]}."))

    for q, key, unit in [("Who has more hat tricks?", "hattricks", ""),
                         ("Who has more free kick goals?", "freekicks", " direct free kick goals")]:
        qs.append((q, most(key,
                           lambda w, x, unit=unit: f"{SHORT[w]}, with {x[w]}{unit}.",
                           lambda o, x: f"{SHORT[o]} has {x[o]}.",
                           lambda n, unit=unit: f"They are level on {n}{unit or ' each'}.")))

    pct = {k: 100 * P[k]["pens"] / (P[k]["pens"] + P[k]["pens_missed"]) for k in P}
    cw = leader(round(pct["r"], 1), round(pct["m"], 1)) or "r"
    qs.append(("Who has more penalty goals?", most(
        "pens",
        lambda w, x: f"{SHORT[w]}, with {x[w]}.",
        lambda o, x: f"{SHORT[o]} has {x[o]}.",
        lambda n: f"They are level on {n}.")
        + f" Ronaldo has missed {R['pens_missed']} and Messi {M['pens_missed']}, so {SHORT[cw]} has scored "
          f"{pct[cw]:.1f} percent of his penalties and {SHORT[OTHER[cw]]} {pct[OTHER[cw]]:.1f} percent. "
          "Shootouts are not counted."))

    qs.append(("Who has more headed goals?", most(
        "headers",
        lambda w, x: f"{SHORT[w]}, with {x[w]}.",
        lambda o, x: f"{SHORT[o]} has {x[o]}.",
        lambda n: f"They are level on {n}.")))

    sw = leader(R["best_season"], M["best_season"])
    yw = leader(R["best_year"], M["best_year"])
    if sw and sw == yw:
        o = OTHER[sw]
        a = (f"{SHORT[sw]}, with {P[sw]['best_season']} goals in {P[sw]['best_season_name']} and "
             f"{P[sw]['best_year']} in {P[sw]['best_year_name']}. {SHORT[o]}'s best are {P[o]['best_season']} "
             f"in {P[o]['best_season_name']} and {P[o]['best_year']} in {P[o]['best_year_name']}.")
    else:
        a = (f"Ronaldo's best are {R['best_season']} goals in {R['best_season_name']} and {R['best_year']} "
             f"in {R['best_year_name']}. Messi's are {M['best_season']} in {M['best_season_name']} and "
             f"{M['best_year']} in {M['best_year_name']}.")
    qs.append(("Who scored more in a single season and a single year?", a))

    measures = [("goals", R["goals"], M["goals"]),
                ("goals per game", round(G["r"], 2), round(G["m"], 2)),
                ("assists", R["assists"], M["assists"]),
                ("international goals", R["intl_goals"], M["intl_goals"]),
                ("UEFA Champions League titles", T["r"]["championsleague"], T["m"]["championsleague"]),
                ("Ballon d'Or awards", R["bdo"], M["bdo"]),
                ("team trophies", T["r"]["total"], T["m"]["total"]),
                ("FIFA World Cup titles", T["r"]["worldcup"], T["m"]["worldcup"]),
                ("hat tricks", R["hattricks"], M["hattricks"])]
    leads = {"r": [], "m": []}
    for label, r, m in measures:
        w = leader(r, m)
        if w:
            leads[w].append(label)
    a = "There is no official measure."
    for k in ("r", "m"):
        if leads[k]:
            a += f" {SHORT[k]} leads in {series(leads[k])}."
    if len(R["title_countries"]) > 1:
        every = " with every club he has played for," if R["titles_everywhere"] else ""
        a += (f" Ronaldo has won titles{every} in {word(len(R['title_countries']))} countries: "
              f"{series(R['title_countries'])}.")
    qs.append(("Who is better, Messi or Ronaldo?", a))
    return qs


# ----------------------------------------------------------------------------
# Regions
# ----------------------------------------------------------------------------

def regions(data, values):
    if "messi" not in data:
        return {}
    R, M = ronaldo(data, values), messi(data)
    d = page_date(data)
    TR, TM = R["trophies"], M["trophies"]
    r = {}

    r["mvr.stamp"] = [f"Ronaldo as of {values['meta.updated.long']}. Messi as of {values['messi.updated.long']}."]

    r["mvr.players"] = (['<div class="players">'] + profile(R, "r", R["born"], _age(R["born"], d))
                        + profile(M, "m", M["born"], _age(M["born"], d)) + ["</div>",
                        f'<div class="score"><div>{R["goals"]:,}</div><span>Career goals</span>'
                        f'<div>{M["goals"]:,}</div></div>'])

    r["mvr.questions"] = [f'<div class="qa"><h3>{q}</h3><p>{htmllib.escape(a, quote=False)}</p></div>'
                          for q, a in questions(data, R, M)]

    r["mvr.totals"] = cmp_table([
        ("Games", R["apps"], M["apps"], "hi"),
        ("Goals", R["goals"], M["goals"], "hi"),
        ("Goals per game", gpg(R["goals"], R["apps"]), gpg(M["goals"], M["apps"]), "hi"),
        ("Assists", R["assists"], M["assists"], "hi"),
        ("Club games", R["club_apps"], M["club_apps"], "hi"),
        ("Club goals", R["club_goals"], M["club_goals"], "hi"),
        ("International caps", R["intl_apps"], M["intl_apps"], "hi"),
        ("International goals", R["intl_goals"], M["intl_goals"], "hi"),
        ("Hat tricks", R["hattricks"], M["hattricks"], "hi"),
        ("Penalty goals", R["pens"], M["pens"], "hi"),
        ("Non penalty goals", R["goals"] - R["pens"], M["goals"] - M["pens"], "hi"),
        ("Direct free kick goals", R["freekicks"], M["freekicks"], "hi"),
        ("Headed goals", R["headers"], M["headers"], "hi"),
    ], "Career totals")

    def others(P, national):
        return [f"{t['name']} ({', '.join(t['years'])})" for nat, items in P["trophy_groups"]
                if nat == national for t in items if t["kind"] == "other"]
    also = []
    for label, national in (("Club", False), ("National team", True)):
        parts = [f"{SHORT[k]}'s {series(others(P, national))}" for k, P in (("r", R), ("m", M))
                 if others(P, national)]
        if parts:
            also.append(f" {label} trophies also include {series(parts)}.")
    r["mvr.trophies"] = cmp_table([
        ("Senior team trophies", TR["total"], TM["total"], "hi"),
        ("Club trophies", TR["club"], TM["club"], "hi"),
        ("National team trophies", TR["national"], TM["national"], "hi"),
        ("League titles", TR["league"], TM["league"], "hi"),
        ("UEFA Champions League", TR["championsleague"], TM["championsleague"], "hi"),
        ("FIFA Club World Cup", TR["clubworldcup"], TM["clubworldcup"], "hi"),
        ("UEFA Super Cup", TR["uefasupercup"], TM["uefasupercup"], "hi"),
        ("Domestic cups", TR["cup"], TM["cup"], "hi"),
        ("Domestic super cups", TR["supercup"], TM["supercup"], "hi"),
        ("FIFA World Cup", TR["worldcup"], TM["worldcup"], "hi"),
        ("European Championship / Copa America", TR["continental"], TM["continental"], "hi"),
    ], "Team trophies") + note(
        "Senior trophies only, super cups included, as on ronaldostats.app." + "".join(also))

    r["mvr.awards"] = cmp_table([
        ("Ballon d'Or", R["bdo"], M["bdo"], "hi"),
        ("The Best FIFA Men's Player", R["best"], M["best"], "hi"),
        ("FIFA World Player of the Year", R["worldplayer"], M["worldplayer"], "hi"),
        ("European Golden Shoe", R["goldenshoe"], M["goldenshoe"], "hi"),
        ("UEFA Men's Player of the Year", R["uefa_player"], M["uefa_player"], "hi"),
        ("UEFA Club Footballer of the Year", R["uefa_club"], M["uefa_club"], "hi"),
        ("UEFA Champions League top scorer", R["cl_top"], M["cl_top"], "hi"),
        ("League top scorer awards", R["league_top_count"], M["league_top_count"], "hi"),
        ("FIFA World Cup Golden Ball", R["wc_ball"], M["wc_ball"], "hi"),
        ("FIFA Club World Cup Golden Ball", R["cwc_ball"], M["cwc_ball"], "hi"),
        ("Top scorer at a European Championship / Copa America", R["continental_top"], M["continental_top"], "hi"),
        ("FIFA Puskas Award", R["puskas"], M["puskas"], "hi"),
    ], "Individual awards") + note(
        "League top scorer awards: for Ronaldo " + series(award_phrase(n, c) for n, c in R["league_top"])
        + "; for Messi " + series(award_phrase(n, c) for n, c in M["league_top"]) + ".")

    r["mvr.ballondor"] = cmp_table([
        ("Wins", R["bdo"], M["bdo"], "hi"),
        ("Runner up", R["bdo_second"], M["bdo_second"], "hi"),
        ("Third place", R["bdo_third"], M["bdo_third"], "hi"),
        ("Shortlisted", R["bdo_noms"], M["bdo_noms"], "hi"),
        ("Winning years", ", ".join(R["bdo_years"]), ", ".join(M["bdo_years"]), None),
    ], "Ballon d'Or")

    h2h, cl = data["versus"]["head_to_head"], data["versus"]["clasico"]
    r["mvr.headtohead"] = sub("All meetings") + cmp_table([
        ("Matches", h2h["matches"], h2h["matches"], None),
        ("Wins", h2h["ronaldo"]["wins"], h2h["messi"]["wins"], "hi"),
        ("Draws", h2h["draws"], h2h["draws"], None),
        ("Goals", h2h["ronaldo"]["goals"], h2h["messi"]["goals"], "hi"),
        ("Assists", h2h["ronaldo"]["assists"], h2h["messi"]["assists"], "hi"),
    ], "Head to head") + sub("El Clasico") + cmp_table([
        ("Matches", cl["ronaldo"]["matches"], cl["messi"]["matches"], None),
        ("Goals", cl["ronaldo"]["goals"], cl["messi"]["goals"], "hi"),
        ("Goals per game", gpg(cl["ronaldo"]["goals"], cl["ronaldo"]["matches"]),
         gpg(cl["messi"]["goals"], cl["messi"]["matches"]), "hi"),
    ], "El Clasico")

    teams24 = data["versus"]["teams_2024"]
    r["mvr.continental"] = cmp_table([
        ("Tournament", "European Championship", "Copa America", None),
        ("Editions played", len(R["intl"]["continental_editions"]), len(M["intl"]["continental_editions"]), None),
        ("Years", ", ".join(map(str, R["intl"]["continental_editions"])),
         ", ".join(map(str, M["intl"]["continental_editions"])), None),
        ("Titles", TR["continental"], TM["continental"], "hi"),
        ("Teams at the 2024 edition", teams24["euros"], teams24["copa"], None),
    ], "European Championship and Copa America")

    r["mvr.leagues"] = cmp_table([
        ("Seasons in the Premier League, La Liga or Serie A", R["big3_seasons"], M["big3_seasons"], "hi"),
        ("Span", R["big3_span"], M["big3_span"], None),
        ("Goals in those leagues", R["big3_goals"], M["big3_goals"], "hi"),
        ("Seasons in Ligue 1", 0, data["messi"]["top_leagues"]["ligue1_seasons"], None),
        ("Last match for a European club", R["last_european"], M["last_european"], None),
    ], "Top leagues")

    r["mvr.international"] = cmp_table([
        ("Team", "Portugal", "Argentina", None),
        ("Caps", R["intl_apps"], M["intl_apps"], "hi"),
        ("Goals", R["intl_goals"], M["intl_goals"], "hi"),
        ("Goals per game", gpg(R["intl_goals"], R["intl_apps"]), gpg(M["intl_goals"], M["intl_apps"]), "hi"),
        ("Hat tricks", R["intl_hattricks"], M["intl_hattricks"], "hi"),
        ("First cap", R["intl"]["first_cap"], M["intl"]["first_cap"], None),
        ("Last cap", R["intl"].get("retired", "Active"), M["intl"].get("retired", "Active"), None),
        ("FIFA World Cups played", R["intl"]["world_cups_played"], M["intl"]["world_cups_played"], None),
        ("FIFA World Cups scored in", R["intl"]["world_cups_scored_in"], M["intl"]["world_cups_scored_in"], "hi"),
        ("FIFA World Cup goals", R["wc"], M["wc"], "hi"),
        ("FIFA World Cup titles", TR["worldcup"], TM["worldcup"], "hi"),
        ("European Championship / Copa America goals", R["continental"], M["continental"], "hi"),
        ("European Championship / Copa America titles", TR["continental"], TM["continental"], "hi"),
        ("UEFA Nations League goals", R["nl_goals"], "n/a", None),
        ("UEFA Nations League titles", R["nl_titles"], "n/a", None),
    ], "International career") + note(
        "The UEFA Nations League is for European national teams, so Argentina do not play in it.")

    peaks = ['<div class="tbl"><table class="cmp"><caption class="sr">Best seasons</caption>', CMP_HEAD, "<tbody>"]
    for label, key in [("Most goals in a club season", "best_season"),
                       ("Most league goals in a season", "best_league"),
                       ("Most goals in a calendar year", "best_year"),
                       ("Most UEFA Champions League goals in a season", "cl_best")]:
        rc, mc = lead_cells(R[key], M[key])
        peaks.append(f'<tr><td{rc}>{R[key]} <span class="s">{R[key + "_name"]}</span></td>'
                     f'<th scope="row">{label}</th>'
                     f'<td{mc}>{M[key]} <span class="s">{M[key + "_name"]}</span></td></tr>')
    peaks.append("</tbody></table></div>")
    r["mvr.seasons"] = peaks

    r["mvr.clubs"] = two(sub("Cristiano Ronaldo") + club_table(R["teams"], "Cristiano Ronaldo"),
                         sub("Lionel Messi") + club_table(M["teams"], "Lionel Messi"))

    miami = next(row for row in data["messi"]["seasons"] if "from" in row)
    miami_seasons = dt.date.fromisoformat(data["messi"]["updated"]).year - miami["from"] + 1
    r["mvr.byseason"] = two(sub("Cristiano Ronaldo") + season_table(R["seasons"], "Cristiano Ronaldo"),
                            sub("Lionel Messi") + season_table(M["seasons"], "Lionel Messi")) + note(
        f"All competitions. {M['names'][miami['team']]} plays calendar year seasons, so Messi's "
        f"{word(miami_seasons)} seasons there are shown as one row.")

    r_blocks = [(name, items) for (tid, name), (_, items) in zip(RONALDO_TEAMS, R["trophy_groups"]) if items]
    m_blocks = [(M["names"][g["team"]], g["items"]) for g in data["messi"]["trophies"]]
    youth = data["messi"]["youth_titles"]
    r["mvr.trophylist"] = two(trophy_list("Cristiano Ronaldo", TR["total"], r_blocks),
                              trophy_list("Lionel Messi", TM["total"], m_blocks)) + note(
        "Not counted for Messi: " + series(f"the {y['years'][0]} {y['name']}" for y in youth)
        + ", which were won with Argentina's youth teams.")

    return {k: "\n".join(v) for k, v in r.items()}


# ----------------------------------------------------------------------------
# Validation and the messi command
# ----------------------------------------------------------------------------

def validate(data):
    if "messi" not in data:
        return []
    errors = []
    m = data["messi"]
    try:
        dt.date.fromisoformat(m["updated"])
    except ValueError:
        errors.append(f"messi.updated is not a date: {m['updated']}")
    ids = {t["id"] for t in m["teams"]}
    for t in m["teams"]:
        for k in ("apps", "goals", "hattricks"):
            if not isinstance(t[k], int) or t[k] < 0:
                errors.append(f"messi {t['id']}: {k} must be a whole number")
        if t["hattricks"] * 3 > t["goals"]:
            errors.append(f"messi {t['id']}: {t['hattricks']} hat tricks need more than {t['goals']} goals")
        if t.get("national"):
            continue
        rows = [r for r in m["seasons"] if r["team"] == t["id"]]
        for k in ("apps", "goals"):
            if sum(r[k] for r in rows) != t[k]:
                errors.append(f"messi {t['id']}: seasons give {sum(r[k] for r in rows)} {k}, the team {t[k]}")
    for r in m["seasons"]:
        if r["team"] not in ids:
            errors.append(f"messi season row for unknown team {r['team']}")
    goals = sum(t["goals"] for t in m["teams"])
    c = m["career"]
    if c["penalties"] + c["freekicks"] > goals:
        errors.append("messi: penalties and free kicks exceed his goals")
    for who, n in (("Ronaldo", data.get("penalties_missed")), ("Messi", c.get("penalties_missed"))):
        if not isinstance(n, int) or n < 0:
            errors.append(f"{who}: missed penalties must be a whole number")
    if c["headers"] > goals - c["penalties"] - c["freekicks"]:
        errors.append("messi: headed goals exceed his open play goals")
    for g in m["trophies"]:
        if g["team"] not in ids:
            errors.append(f"messi trophies for unknown team {g['team']}")
        for t in g["items"]:
            if t["kind"] not in KINDS:
                errors.append(f"messi trophy {t['name']}: unknown kind {t['kind']}")
    aw = m["awards"]
    podiums = len(aw["ballondor"]) + aw["ballondor_second"] + aw["ballondor_third"]
    if data["ballon_dor_next_most"]["nominations"] < podiums:
        errors.append("messi: fewer Ballon d'Or nominations than podium finishes")
    h = data["versus"]["head_to_head"]
    if h["ronaldo"]["wins"] + h["messi"]["wins"] + h["draws"] != h["matches"]:
        errors.append("head to head: wins and draws do not add up to the matches")
    return errors


def apply_match(data, args):
    """One Messi match: a game for his team, and whatever he scored or set up."""
    m = data["messi"]
    team = next((t for t in m["teams"] if t["id"] == args.team), None)
    if team is None:
        sys.exit(f"Unknown Messi team {args.team}: use one of "
                 + ", ".join(t["id"] for t in m["teams"]))
    if min(args.goals, args.assists, args.penalties, args.freekicks, args.headers, args.missed_penalties) < 0:
        sys.exit("Counts cannot be negative.")
    if args.penalties + args.freekicks + args.headers > args.goals:
        sys.exit("More penalties, free kicks and headers than goals.")
    team["apps"] += 1
    team["goals"] += args.goals
    if args.goals >= 3:
        team["hattricks"] += 1
    if not team.get("national"):
        row = [r for r in m["seasons"] if r["team"] == team["id"]][-1]
        row["apps"] += 1
        row["goals"] += args.goals
    c = m["career"]
    c["assists"] += args.assists
    c["penalties"] += args.penalties
    c["penalties_missed"] += args.missed_penalties
    c["freekicks"] += args.freekicks
    c["headers"] += args.headers
    m["updated"] = (args.date or dt.date.today()).isoformat()
    return data
