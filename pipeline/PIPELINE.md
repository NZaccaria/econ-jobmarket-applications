# Applications pipeline

How openings get found, triaged, and turned into applications. Read this first
in a new Claude session; it is the whole state of the system.

## The one rule

**Nothing is ever deleted or hidden.** Every listing seen stays in
`openings.csv` for good. The triage decides ordering and which checkbox starts
ticked. It never decides what you get to see.

This exists because the costs are asymmetric. Skimming twenty listings you will
reject takes half a minute. Silently dropping the one posting that was actually
your job costs you the job, and you never find out it happened.

The corollary, and the reason the filter looks the way it does: **field never
excludes anything.** A micro theory ad is worth an application because
departments are more flexible than they advertise and applications are close to
free. What disqualifies a listing is the *kind of post* (predoc, PhD student,
adjunct, a chair with no junior rank), never its topic. Field only sets ordering
and how much tailoring effort to spend.

## Where things live

| Thing | Where | Who writes it |
|---|---|---|
| Catalog of every listing ever seen | `pipeline/openings.csv` | script only |
| Full ad text, one file per listing | `pipeline/ads/<uid>.txt` | script only |
| Scoring and category knobs | `pipeline/config.yml` | you |
| Last-run counts, for the sanity check | `pipeline/state.json` | script only |
| **Inbox** tab (tick boxes here) | Google Sheet | script writes, you tick |
| **Applications** tab (the tracker) | Google Sheet | script appends, you maintain |
| Google credentials | `pipeline/service_account.json` | never commit it |

The spreadsheet id goes in `pipeline/config.yml` under `sheet_id`.

There is no local `.xlsx` any more, on purpose. The Google Sheet is the single
source of truth so it is always the current version and supervisors can read it
without anyone mailing files around.

## The loop

```
              fetch.py                     promote.py
   sources ─────────────► Inbox ──ticked───► Applications   (status: promoted)
                            │
                            └──unticked────► Parked         (status: parked)
```

Four states, one direction of travel: `new` → `promoted` or `parked`, plus
`expired` when a deadline passes. **Every promote run empties the Inbox**, so
whatever is in it next time is genuinely new since you last looked. You never
re-read the same list, and a re-score cannot drag an old row back in front of
you.

```
python3 pipeline/fetch.py        # both sources -> catalog -> Inbox
                                    # you tick boxes in the Inbox tab
python3 pipeline/promote.py      # ticked -> Applications, rest -> Parked
```

Both take `--dry-run`. `fetch.py --no-sheet` updates the catalog only.

### The three tabs

- **Inbox** — only things you have not decided on. Pre-ticked unless the row is
  a wrong kind of post. Sorted by bucket then score, with an **Added** column
  showing when it first appeared.
- **Parked** — what you left unticked. Nothing is lost: tick a row here and the
  next `promote.py` sends it to Applications, whenever you change your mind.
  Nothing on this tab is pre-ticked, and `promote.py` reads its ticks on every
  run, not just the run after parking.
- **Applications** — your tracker. Applied / Interview / Flyout / Offer start
  FALSE; you tick Applied yourself when you actually submit.

### The Promote button (no terminal)

`pipeline/AppsScript.gs` puts a **Job Market -> Promote ticked rows** menu in
the spreadsheet. Install once: Extensions -> Apps Script, replace `Code.gs` with
that file, Save, reload the sheet. First click asks for authorisation.

It needs no credentials and no network: it only moves rows between tabs. That
works because **the sheet is the source of truth for decisions**. `fetch.py`
calls `sheet.decisions()` and reads which uids sit on Applications (promoted)
and Parked (parked), so a row moved in the spreadsheet is never put back in the
Inbox by the next nightly run. A row you delete from Applications by hand
returns to the Inbox as undecided, which is the sane reading of that gesture.

`promote.py` still exists and does exactly the same thing from the terminal.
Use whichever you prefer; they cannot disagree, because both write to the same
tabs and neither owns the state.

### What you actually do

1. Open **Inbox**, on a laptop or the Sheets phone app. New listings appear
   there overnight and simply wait, ticked or unticked, until you act.
2. Untick what you do not want. Tick anything in the skip rows you do want.
3. **Job Market -> Promote ticked rows** (or `promote.py`). Ticked rows land in
   Applications, the rest go to Parked, and the Inbox is empty.
4. Tick **Applied** yourself when you submit, and fill the Letter Writer
   columns. That is what makes deadline tracking possible later.

Ask Claude "what does the Mannheim ad actually want?" and it reads
`pipeline/ads/`. The full text is local, so no browser and no login.

### The daily GitHub Action

`.github/workflows/daily.yml` runs `fetch.py` at **01:00 UTC** daily and
commits the updated catalog back. It never runs `promote.py`: promoting is your
decision, not a robot's.

GitHub cron is always UTC and does **not** follow daylight saving, so 01:00 UTC
is 03:00 Amsterdam in summer (CEST) and 02:00 in winter (CET). It is set that
early on purpose: Actions schedules are best-effort and can lag from minutes to
a couple of hours at peak, so an overnight slot leaves a long runway to be
finished before an 08:30 start. Landing overnight also keeps it away from you:
`fetch.py` rewrites the Inbox tab wholesale, so a run firing mid-review would
clobber ticks you had just made.

Measured before enabling, not estimated: one run is **53s wall clock, billed as
1 minute**, so daily costs ~30 min/month against the 2000 free private-repo
minutes. With `fare-watch` also running that is roughly 150/2000, about 8%.

Credentials come from repo secrets, not the repo: `GOOGLE_SERVICE_ACCOUNT`
holds the service account JSON (`common.open_sheet()` falls back to it when
`service_account.json` is absent, which it always is in CI) and `SHEET_ID`
holds the spreadsheet id.

Two things to remember. GitHub disables scheduled workflows after **60 days of
repository inactivity**; the daily commit only happens when listings change, so
during a quiet stretch check that the workflow is still `active`. And Actions
cron drifts by tens of minutes at peak times, which for a daily job is fine.

To test a change without waiting: `gh workflow run daily.yml`.

### When to run the scraper

Once a day is right: JOE publishes in monthly issues and EJM trickles, so
polling more often buys nothing. Run it **early, around 06:00**, for one
practical reason: `fetch.py` rewrites the Inbox tab wholesale, so a run that
fires while you are mid-review can clobber ticks you have just made. A fixed
early slot never collides with you.

Until the GitHub Action exists, run `fetch.py` by hand when you sit down. It is
idempotent and preserves your ticks, so running it twice costs nothing.

## The two sources

**JOE** (`aeaweb.org/joe/listings`) publishes an XLSX export the pipeline reads
directly. No scraping, no login. It carries institution, department, title,
section, JEL codes, locations, deadline and the complete ad text. This source is
solid. Roughly 171 listings in early September; expect well over a thousand by December.

**EJM** has three separate boards and this matters more than anything else here:

| URL | What it is | Fetched as |
|---|---|---|
| `/positions` | **"All regular postings"**, the real faculty job market | `EJM` |
| `/market` | the RA and pre-doc board | `EJM-RA` |

An earlier version of this pipeline scraped `/market` and therefore **missed the
entire faculty market**, including an open-rank macro/monetary position at
Williams College. The tell was that `/market`'s position-type dropdown offers
only "Doctoral student" and "Research Assistant". If EJM ever looks thin, check
which board you are on before anything else.

`/positions` paginates at 50 via `?page=N` and states its own total
("92 positions found"). `fetch_ejm` pages until exhausted and then **asserts the
parsed count equals the stated total**, raising if not. That assertion is the
single most valuable line in the file: it converts a silently truncated listing,
which looks exactly like a quiet day, into a loud failure.

There is also an EJM API at <https://econjobmarket.org/pages/backend>, unexplored.
Worth a look if the HTML parser becomes annoying to maintain.

### Verifying coverage

JOE was cross-checked by requesting `?ListingsForm[lpp]=all` and diffing the page
against the catalog: 171 on the page, 171 in the catalog, zero either way. JOE's
`issue=2026-02` is the whole autumn cycle ("all listings published since August 1,
2026"), not one month, so a single issue is correct and complete.

Re-run that check if coverage is ever in doubt:

```bash
curl -s "https://www.aeaweb.org/joe/listings?ListingsForm%5Blpp%5D=all" -o /tmp/joe_all.html
python3 -c "
import re,csv
page=set(re.findall(r'JOE_ID=([0-9]{4}-[0-9]{2}_[0-9]+)',open('/tmp/joe_all.html',encoding='utf8',errors='replace').read()))
cat={r['uid'].split(':',1)[1] for r in csv.DictReader(open('pipeline/openings.csv',encoding='utf-8')) if r['source']=='JoE'}
print('on page not in catalog:',page-cat); print('in catalog not on page:',cat-page)"
```

### The failure that actually matters

A scraper returning zero looks exactly like a quiet day. Two guards:

1. `fetch.py` compares each source against its last-run count in `state.json` and
   **refuses to write** if one drops below `min_fraction_of_last_run` (default
   50%) or errors. It exits non-zero.
2. EJM's parsed count must equal EJM's own stated total, or it raises.

## Cross-posted openings

Most openings eventually appear on both JOE and EJM. When one does, the Inbox
shows **one row**, flagged in the **Both sites** column as
`also on JoE (joe:2026-02_...)`. Both listings stay in `openings.csv`; only the
Inbox view collapses. Currently 11 collapsed, 230 single-site.

### Only ever across platforms

Two listings on the same site are **never** merged. The Atlanta Fed advertises
"Research Economist" three times on each site, and those are three separate
searches, the first hiring two people:

| field | JEL |
|---|---|
| macro / monetary ("hire two economists") | E0 E5 E6 |
| labor | J0 |
| household finance | G5 |

Merging within a platform would have deleted two real searches and several jobs.

### What has to agree

Same institution, same title, and the **same deadline**. The deadline is the
real gate: if the two sites disagree about it, the listings stay as two rows,
which is harmless. That excludes Tennessee Tech (22 Nov vs 25 Dec), OECD (15 Nov
vs 1 Nov), Princeton (31 Dec vs 1 Jan) and Northwestern's managerial post.

Ad body text is **not** thresholded. The two sites format ads so differently
that Brown's identical posting scores 0.07 similarity, so an absolute cutoff
would reject obvious matches. Body text is used only to pick which partner goes
with which when one employer runs several near-identical ads, and there it is
decisive: the Fed's correct pairs score 1.00 against 0.53-0.72 for the wrong
pairings. Assignment is greedy 1:1 on that score.

Institution matching: 93% on the full name, or the same type word plus 60%
shared distinctive tokens ("Tennessee Technological University" ~ "Tennessee
Tech University"). **Do not treat "University" and "College" as noise**, or
"Northwestern College" (Iowa) becomes "Northwestern University" (Illinois),
whose economics ads are 94% title-similar.

Thresholds live in `config.yml` under `duplicates`.

## Tests

```
python3 -m pytest pipeline/test_pipeline.py -q     # or run the file directly
```

Every case is a bug that actually shipped, or the boundary that separates it
from a correct classification. They are pure functions: no network, no
credentials. The CI job runs them before touching the spreadsheet.

Two of them are cross-language: the spreadsheet button resolves columns by
header **name**, and a test asserts every name it uses exists in `sheet.py`.
Renaming a header therefore fails the build instead of silently writing the
wrong fields into Applications.

Worth knowing: a test that has never failed proves nothing. When adding one,
reintroduce the bug and check it goes red. Doing that here found a test of mine
that was blind, because the case it covered was actually protected by a
different guard than the one I thought.

## Module layout

| File | Holds |
|---|---|
| `sources.py` | where listings come from: JOE's XLSX export, EJM's HTML |
| `triage.py` | what they are worth: category, score, cross-post detection |
| `sheet.py` | the spreadsheet: Inbox, Parked, Applications, formatting |
| `common.py` | config, catalog I/O, auth, parsing helpers |
| `fetch.py` | orchestration only |
| `promote.py` | the terminal equivalent of the spreadsheet button |
| `AppsScript.gs` | the spreadsheet button |

## Formatting

The sheet reproduces the Tilburg template's look, and the values were read off
the original rather than guessed:

- header band `#F46524`, rows alternating white and `#FFE6DD`
- header row bold 11pt, body 10pt, first two rows frozen
- **Institution bold** on every tab
- **Real tickboxes, never typed TRUE/FALSE**, on all ten logical columns of the
  Applications tab: Applied, Interview, Flyout, Offer, Letter Writer 1-4,
  Signal JOE, Signal EJME (zero-indexed 0-3, 15-18, 20-21, in `APP_BOOL_COLS`)

**Application URL is a real hyperlink**, blue and underlined, written as a
plain string carrying a link rather than a `HYPERLINK()` formula, so the cell
still reads as a URL if you copy it out. That is how the template does it. Each
cell needs its own uri, so it goes out as one `updateCells` request with one row
per listing.

**Notes is yours and is never written to.** The pipeline's own provenance
(`bucket A · score 46`, and which listings were bundled) goes in **Description**.

`format_applications()` reapplies all of it after every append, so formatting
survives new rows. Banded ranges cannot overlap, so `_drop_banding()` removes
the existing ones first; skipping that step makes the API reject the request.

## Google Sheets notes

Auth is a Google service account, shared on the sheet as Editor (see README). It works headless, so the same code runs on the
laptop and later in CI. The key file is gitignored; in GitHub Actions it goes in
as the `GOOGLE_SERVICE_ACCOUNT` secret, which `common.open_sheet()` already reads.

The API allows **60 write requests per minute**. Delete rows in one batched
request, never in a loop: clearing 200 template rows one at a time returns 429
halfway and leaves the tab torn. `sheet._delete_rows_batched` does this properly.

## Not built yet

- **GitHub Actions daily run.** Estimated ~45-60 min/month against the 2,000
  free private-repo minutes; `fare-watch` already uses roughly 120. Not a
  constraint. Needs the folder to be a private repo first.
- **Telegram notifications.** Deliberately parked. If added, they should be
  exception-based (scraper broken, deadline within three days and not submitted,
  weekly digest), never a per-listing feed, which is noise you learn to ignore
  exactly before the message that mattered.
- **Deadline and reference-letter alarms.** The columns exist and promote.py
  fills the deadline. Nothing reads them yet.
- **Other sources.** Currently JOE and EJM only. AEA and EJM cover most of the
  market but not everything: some European departments post only on their own
  pages, and Australian and Latin American posts are patchy.
