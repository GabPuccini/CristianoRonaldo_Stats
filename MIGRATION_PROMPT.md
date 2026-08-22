# Migration to a single source of truth

Goal: stop hand editing numbers in six HTML files. `data/ronaldo.json` becomes
the only place a statistic is written, and `scripts/update_stats.py` rewrites
every published figure from it.

Run this in five phases, checking after each one. Phase 3 touches every page.

## Phase 1: build the real dataset

Create `data/ronaldo.json` in the shape of `data/ronaldo.example.json`, but
populate every value by extracting it from the existing HTML, which is the
current source of truth:

* the six teams with their years and assists, from the home page career table
* every season row from the club table on `goalsbyseason.html`, including the
  apps and goals split across the League, National Cup, League Cup,
  Continental and Other columns
* the Portugal senior year rows from the national team table
* every calendar year row from `goalsbyyear.html` with its age
* the competition tallies, body part splits and opponent data from the `DATA`
  object in `dashboard.html`
* penalties, free kicks and hat tricks from the home page table

Mark the Sporting CP B reserve row `"in_career": false`. Those two appearances
show on the season page but sit outside the headline 1,330.

Then run `python scripts/update_stats.py check`. It must report that all totals
reconcile at 976 goals, 1,330 appearances and 291 assists. If it does not, the
extraction is wrong, not the script. Never change a published number to make it
fit, and never touch the assist total, which is counted by hand and is
deliberately higher than other trackers.

## Phase 2: prove the engine reproduces the site

Before touching any page, render every value the engine computes and diff it
against the numbers currently printed in the HTML. Resolve every disagreement
before moving on.

## Phase 3: add the markers, one page at a time

* a single number becomes `<b data-stat="career.goals">976</b>`, keeping the
  existing tag, classes and text exactly as they are
* an attribute carrying a number gets
  `data-stat-attr="aria-valuenow:career.goals.raw"` or
  `data-stat-attr="style:career.fillstyle"`
* a table body or chart array gets wrapped in
  `<!-- STATS:BEGIN table.years -->` and `<!-- STATS:END table.years -->`
* the updated date gets `data-stat="meta.updated.long"` plus
  `data-stat-attr="datetime:meta.updated.iso"`

Do not change a single visible character, class, tag or piece of layout. Only
attributes and comments are added. After each page run
`python scripts/update_stats.py build` then `git diff` on that page: the only
differences must be the markers. If a number moves, the dataset is wrong for
that figure and the dataset gets fixed, not the HTML.

Order: `goalsbyyear.html`, `goalsbyseason.html`, `index.html`,
`dashboard.html`, `timeline.html`, `achievements.html`.

## Phase 4: the text that also carries numbers

Figures appear inside sentences, meta descriptions, JSON-LD blocks and page
titles. Mark the ones in the body with `data-stat` spans. For the title, the
meta description, the Open Graph tags and the JSON-LD, extend
`update_stats.py` with a list of regular expression replacements driven by the
same values dictionary. Add a test that fails if any published number appears
in a page without being either marked or covered by a replacement.

## Phase 5: dry run

    python scripts/update_stats.py goal --team alnassr --comp league \
        --competition-label "Saudi Pro League" --opponent "Al Hilal" --new-appearance

Review the full `git diff`: every number that should have moved must have
moved, on every page, and nothing else may have changed. Then
`python scripts/update_stats.py undo` and confirm `git diff` is empty.
