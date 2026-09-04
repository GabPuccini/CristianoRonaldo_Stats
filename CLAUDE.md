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

`sitemap.xml` is driven too: the `lastmod` of each of the six statistics pages
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
tally into two and the chart would show both. The 22 valid labels are:

    La Liga                 Champions League        Premier League
    Saudi Pro League        Serie A                 Euro qualifiers
    World Cup qualifiers    Other cup competitions  Copa del Rey
    Friendlies              AFC Champions League    Nations League
    Euros                   FA Cup                  World Cup
    Coppa Italia            League Cup              King's Cup
    Primeira Liga           Confederations Cup      Europa League
    Taca de Portugal

Anything that is not on that list belongs in `Other cup competitions`, which is
how the chart already groups the Club World Cup, the UEFA Super Cup, domestic
super cups and the Arab Club Champions Cup. Only add a genuinely new label when
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
dashboard. If the side is not on the published opponent lists the script says so
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
   six pages plus `sitemap.xml`, so a diff limited to fewer than seven files
   means something is not wired up and should be looked at rather than
   committed.
3. Commit with a message naming the event, for example
   `Goal 977: Al Nassr v Al Hilal, Saudi Pro League`.
4. Push. Cloudflare serves the new file within a minute or two, and a hard
   refresh with Ctrl Shift R shows it immediately.

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
