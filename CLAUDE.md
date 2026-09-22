# ronaldostats.app

Static site, hand written HTML, CSS and vanilla JavaScript. No framework, no
build step for the markup itself. Hosted on GitHub, served through Cloudflare.

## The one rule about statistics

`data/ronaldo.json` is the single source of truth. **Never edit a number
directly in an HTML file.** Every published figure is either marked with a
`data-stat` attribute or sits inside a `STATS:BEGIN` region, and
`scripts/update_stats.py` rewrites all of them from the JSON.

If you hand edit a number in HTML it will be silently overwritten on the next
update, and worse, the site will disagree with itself across pages.

The `years` rows carry appearances as well as goals. Club appearances are stored
by season, and a season straddles two calendar years, so the yearly figure cannot
be derived and is held instead. A goal or an appearance banks itself to the
calendar year it was played in, and `check` fails if those rows stop adding up to
the career total. That is what feeds the year picker on the home page.

`llms.txt` is driven too. It exists to be read by AI assistants, so a stale
figure there is quoted back as fact rather than being eyeballed by a person,
which is why every number in it is a rule in `file_rules()` and
`check_coverage.py` fails if one is added without one.

`sitemap.xml` is driven too: the `lastmod` of each of the three statistics pages
tracks the update date, since those pages really do change every time. Only
`privacy.html` keeps a hand written date, because the script never touches it.

## When Rambo says Ronaldo scored

Translate the sentence into one command and run it. Do not ask for details he
did not give; use the defaults below and tell him afterwards what you assumed
so he can correct it.

    python scripts/update_stats.py goal --team TEAM --comp SLOT \
        --competition-label "LABEL" --opponent "NAME" --body BODY \
        --type TYPE --new-appearance

### Team values

| He says | `--team` |
|---|---|
| Al Nassr, Saudi league, his club | `alnassr` |
| Portugal, national team, internationals | `portugal` |
| Real Madrid | `realmadrid` |
| Manchester United, United | `manutd` |
| Juventus, Juve | `juventus` |
| Sporting, Sporting CP | `sporting` |

### Competition slot and label

`--comp` is the column in the season table. `--competition-label` is the name
shown on the competitions chart. Common pairs:

| He says | `--comp` | `--competition-label` |
|---|---|---|
| Saudi Pro League, the league | `league` | `Saudi Pro League` |
| King's Cup | `cup` | `King's Cup` |
| AFC Champions League | `cont` | `AFC Champions League` |
| AFC Champions League Two, ACL2 | `cont` | `AFC Champions League Two` |
| Saudi Super Cup, Arab Club Champions Cup, Club World Cup, super cups | `other` | `Other cup competitions` |
| World Cup qualifier | `league` | `World Cup qualifiers` |
| Euro qualifier | `league` | `Euro qualifiers` |
| Nations League | `league` | `Nations League` |
| friendly | `league` | `Friendlies` |
| World Cup | `league` | `World Cup` |
| Euros, European Championship | `league` | `Euros` |

For Portugal the `--comp` slot is ignored, only the label matters.

**The label must match one of these exactly.** They are the labels the site
already publishes on the competitions chart, and `--competition-label` is used
as a dictionary key: an unrecognised label does not fail, it quietly adds a
second row, so `Euro qualifying` alongside `Euro qualifiers` would split one
tally into two and the chart would show both. The 23 valid labels are:

    La Liga                 Champions League        Premier League
    Saudi Pro League        Serie A                 Euro qualifiers
    World Cup qualifiers    Other cup competitions  Copa del Rey
    Friendlies              AFC Champions League    Nations League
    Euros                   FA Cup                  World Cup
    Coppa Italia            League Cup              King's Cup
    Primeira Liga           Confederations Cup      Europa League
    Taca de Portugal        AFC Champions League Two

Anything that is not on that list belongs in `Other cup competitions`, which is
how the chart already groups the Club World Cup, the UEFA Super Cup, domestic
super cups and the Arab Club Champions Cup.

Some labels are stored under their real name and grouped only for display, via
`competition_rollup` in the dataset. The Arab Club Champions Cup, the Saudi
Super Cup and the AFC Champions League Two are all kept that way: filter the
dashboard to Al Nassr and each gets its own bar, while the career chart folds
them into `Other cup competitions`. Use the real name when recording a goal and
the rollup takes care of the rest. The AFC Champions League Two in particular is
a separate competition from the AFC Champions League and must never be added to
it. Only add a genuinely new label when
Ronaldo plays a competition he has never played before, and expect a new bar to
appear on the chart when you do.

### Defaults when he does not say

* `--body right` (right foot, his most common)
* `--type openplay`
* `--new-appearance` on, because a goal implies he played
* season defaults to `meta.current_season`, year defaults to today

Add `--type penalty` or `--type freekick` when he says so, `--body left`,
`--body head` or `--body other`, `--opponent "Name"` whenever he names the
opposition, and `--assists N` if he also created goals.

### Other events

    python scripts/update_stats.py appearance --team alnassr --comp league
    python scripts/update_stats.py assist --team portugal --count 1
    python scripts/update_stats.py hattrick --team alnassr
    python scripts/update_stats.py show     # current headline figures
    python scripts/update_stats.py check    # validate, write nothing
    python scripts/update_stats.py build    # rewrite HTML from current data
    python scripts/update_stats.py undo     # revert the last event

Pass `--opponent "Name"` to `appearance` whenever he names the opposition, the
same as for a goal. A match with no goal still counts against that side, and
leaving it out slowly overstates his goals per game against them on the
dashboard section of the home page. If the side is not on the published opponent
lists the script says so
and moves nothing, since those lists are the teams he has scored against most
rather than a complete record.

### The other scripts

    python scripts/verify_against_html.py   # engine against every published figure
    python scripts/check_coverage.py        # is any figure still hand maintained?
    python scripts/gen_head_rules.py        # only after editing head prose

`verify_against_html.py` compares what the engine computes against what each page
prints, and exits 1 on any disagreement. `check_coverage.py` is the stricter one:
it walks every page and fails if a figure the engine could produce is neither
marked, nor in a region, nor covered by a text rule. Both should be clean before
you commit.

`gen_head_rules.py` rewrites `scripts/head_rules.py`, which drives the figures in
titles, meta descriptions and JSON-LD, where no marker can go. Run it only when
you have changed the wording of a head, and only when the pages already agree
with the data, since it reads the current pages to build its patterns. Every rule
it writes is checked on each build, so a stale one is reported, not ignored.

### Worked examples

> "Ronaldo scored 1 goal in the Saudi Pro League against Al Hilal"

    python scripts/update_stats.py goal --team alnassr --comp league \
        --competition-label "Saudi Pro League" --opponent "Al Hilal" --new-appearance

> "he scored a header for Portugal in a World Cup qualifier against Hungary and got an assist"

    python scripts/update_stats.py goal --team portugal --comp league \
        --competition-label "World Cup qualifiers" --opponent "Hungary" \
        --body head --assists 1 --new-appearance

> "hat trick for Al Nassr in the league, two right foot one penalty, against Al Fateh"

    python scripts/update_stats.py goal --team alnassr --comp league --competition-label "Saudi Pro League" --opponent "Al Fateh" --new-appearance
    python scripts/update_stats.py goal --team alnassr --comp league --competition-label "Saudi Pro League" --opponent "Al Fateh"
    python scripts/update_stats.py goal --team alnassr --comp league --competition-label "Saudi Pro League" --opponent "Al Fateh" --type penalty
    python scripts/update_stats.py hattrick --team alnassr

Note only the first goal of a match carries `--new-appearance`.

## After every update

1. The script prints the new totals and refuses to write if anything fails to
   reconcile. If it fails, read the error, fix the data, do not force it.
2. Check `git diff` and confirm only expected numbers moved. One goal touches all
   three pages plus `sitemap.xml` and `llms.txt`, so a diff limited to fewer
   than five files
   means something is not wired up and should be looked at rather than
   committed.
3. Commit with a message naming the event, for example
   `Goal 977: Al Nassr v Al Hilal, Saudi Pro League`.
4. Push. Cloudflare serves the new file within a minute or two, and a hard
   refresh with Ctrl Shift R shows it immediately.

## The dashboard

The interactive dashboard is a section of `index.html`, not a page. It lives
under `<section id="dashboard">` and `/#dashboard` is the link to it. Chart.js
is fetched only when that section comes within 400px of the viewport, so the
home page does not pay for it on every visit. The three tables under the charts
are the content: they are written from the dataset like any other table and
they read correctly with JavaScript off, so never replace them with canvas only
charts.

`dashboard.html` was retired in September 2026. `/dashboard.html` must keep
returning a 301 to `https://ronaldostats.app/#dashboard`, set as a Cloudflare
Redirect Rule rather than as a file in the repo.

## The timeline

The career timeline is a section of `index.html` too, under
`<section id="timeline">`, reached at `/#timeline`. It sits below the dashboard
and above the quick answers. Photos live in `timeline/` as a jpg and webp pair
named for the slot they fill, and the rules for them are in the writing rules
below.

`timeline.html` was retired in September 2026 and needs the same 301 to
`https://ronaldostats.app/#timeline`.

Each retired page currently has a stub file in the repo holding a canonical and
a meta refresh, which is the weaker stand in. Delete each stub once its
Cloudflare rule is live. Three are outstanding: dashboard, timeline and goals
by year.

## Goals by year

Goals in every calendar year are a section of `index.html` as well, under
`<section id="goalsbyyear">`, reached at `/#goalsbyyear`. It sits directly
below the year picker, where a small sparkline used to be: that sparkline was
removed when the full chart and table arrived, since it said the same thing
less well.

`goalsbyyear.html` was retired in September 2026 and needs a 301 to
`https://ronaldostats.app/#goalsbyyear`.

Chart.js is shared. `chartsReady()` fetches it once and hands it to whichever
sections asked, and `whenNearlyVisible(id, cb)` is what triggers them, so the
goals chart and the dashboard charts cost one request between them and only
when a reader actually reaches one. Add any future chart the same way rather
than loading the library again.

## Site wide writing rules

* British English.
* **Never use em dashes, en dashes or hyphens in visible text.** Hyphens are
  allowed only inside CSS, HTML and code syntax such as attribute names and
  file names. Write "goals per game" and "2002 to 2003", never with a dash.
* Never render statistics as images. Always real HTML tables.
* Timeline photos are shown whole. The box takes the image's own proportions
  rather than forcing a shape onto it, and an image is never scaled up past the
  size it was supplied at, so it stays as sharp as the file. Drop a new photo in
  `timeline/` at whatever proportions it has, portrait or landscape, and add it
  as a `<picture>` with a `webp` source, a `jpg` fallback and the real `width`
  and `height`. Do not add `object-fit: cover` to it: that is what was cutting
  the head and feet off the Sporting debut photo.
* The navigation is duplicated in full on every page on purpose. Do not
  centralise it into a shared include or inject it with JavaScript; static
  markup on every page is deliberate for search engines.
* Keep the light glassmorphism design system: DM Sans for body, Plus Jakarta
  Sans for display, brand blue `#2f56cf`, frosted translucent cards.
* Every page keeps its reduced motion override and its JSON-LD block.

## Validation the script enforces

The update is rejected unless all of these hold:

* calendar years sum to career goals
* body part splits sum to career goals, and per team to that team's goals
* competitions sum to career goals
* penalties plus free kicks never exceed goals, per team and overall
* opponent goals never exceed that team's total

`data/ronaldo.backup.json` holds the previous state so `undo` always works.
