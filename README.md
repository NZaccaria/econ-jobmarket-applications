# econ-jobmarket-applications

Finds economics job openings on **JOE** and **EconJobMarket**, ranks them
against your own research profile, and tracks what you applied to. It can run
itself every night and hand you a spreadsheet where you tick the ones you want.

Built for the 2026--27 academic economics job market, where you send hundreds of
applications and the expensive mistake is not seeing an opening at all.

## The one rule

**Nothing is ever deleted or hidden.** Every listing seen is kept. The score
decides *ordering*, never visibility.

This is the whole design philosophy, and it comes from the costs being lopsided.
Skimming twenty listings you will reject takes half a minute. Silently dropping
the one posting that was actually your job costs you the job, and you never find
out it happened. So the ranking sorts; it does not filter.

The corollary: **your field never excludes anything.** A micro theory ad is
worth an application, because departments are more flexible than they advertise
and applications are close to free. What demotes a listing is the *kind of post*
(pre-doc, PhD student, adjunct, a chair with no junior rank), never its topic.
Field only sets ordering and how much tailoring effort to spend.

## Three levels of setup

Start at 0. It takes two minutes and needs no accounts at all.

| | Setup | What you get |
|---|---|---|
| **0** | clone, edit one file | a ranked `openings.csv` you open in Excel |
| **1** | + a Google service account (~10 min) | tabs you tick, a Promote button, works on your phone, shareable with advisors |
| **2** | + GitHub Actions (~5 min) | it runs itself every night |

---

## Level 0: a ranked list, no accounts

```bash
git clone https://github.com/<you>/econ-jobmarket-applications
cd econ-jobmarket-applications
pip install -r pipeline/requirements.txt

# EDIT pipeline/profile.md - the yaml block near the top is your research.
# The shipped one is a fictional labour economist; it will rank badly for you.

python3 pipeline/fetch.py --no-sheet
```

You now have `pipeline/openings.csv`: every current opening, scored, with the
full ad text saved under `pipeline/ads/`. Open it, sort by `score`, read the
`score_why` column to see why anything ranked where it did.

That is a genuinely useful tool on its own. Everything below is about not having
to re-read the same list every day.

---

## Level 1: the spreadsheet

### What you must do (a browser is required, so this part cannot be automated)

1. **Create a Google Sheet.** Blank is fine; the pipeline builds the tabs. Copy
   its id from the URL: `docs.google.com/spreadsheets/d/`**`THIS-PART`**`/edit`
2. **Create a Google Cloud project** at <https://console.cloud.google.com>.
   Any name.
3. **Enable the Sheets API**:
   <https://console.cloud.google.com/apis/library/sheets.googleapis.com> ->
   Enable. Only this one; the pipeline addresses the sheet by id, so the Drive
   API is not needed.
4. **Credentials -> Create credentials -> Service account.** Name it, Create,
   Done. A service account is a robot identity with its own email address. It
   works with no browser and no consent screen, which is why the nightly run can
   use it.
5. **Keys -> Add key -> Create new key -> JSON.** A file downloads.
6. **Share the Sheet with the service account's email** (it looks like
   `something@your-project.iam.gserviceaccount.com`), as **Editor**. Ignore the
   warning that it looks like a robot. It is.
7. Move the downloaded file to `pipeline/service_account.json`.

That file is a credential. It is gitignored. If one ever reaches a public repo,
deleting it is not enough: rotate the key in Google Cloud, because the old blob
stays in git history.

### What you (or an assistant) then do in the repo

Put the sheet id in `pipeline/config.yml` under `sheet_id`, then:

```bash
python3 pipeline/fetch.py        # builds the Inbox, Parked and Applications tabs
```

### The Promote button

`pipeline/AppsScript.gs` adds a **Job Market -> Promote ticked rows** menu to
the spreadsheet, so you never need a terminal again.

Install it yourself (it needs your Google session): in the sheet, **Extensions
-> Apps Script**, replace `Code.gs` with that file, Save, reload the sheet. The
first click asks for authorisation, which is Google asking whether your own
script may edit your own sheet.

It uses no credentials and no network. It only moves rows between tabs, which
works because the **spreadsheet is the source of truth for decisions**: a uid on
Applications is promoted, one on Parked is parked, and `fetch.py` reads that.
A row you move by hand is respected rather than reverted.

### The daily loop

```
              fetch.py                         Promote button
   sources ─────────────► Inbox ──ticked───────► Applications
                            │
                            └──unticked────────► Parked
```

- **Inbox** holds only what you have not decided on. New listings arrive
  pre-ticked, unless they are the wrong kind of post, and simply wait.
- **Parked** is what you left unticked. Tick a row there any time to bring it
  back on the next promote.
- **Applications** is your tracker: Applied / Interview / Flyout / Offer, letter
  writers, deadlines.

Every promote empties the Inbox, so whatever is in it next time is genuinely new
since you last looked. You never re-read the same list.

---

## Level 2: let it run itself

`.github/workflows/daily.yml` runs the fetch nightly and commits the updated
catalogue. **Your repo must be private**: it will contain which jobs you are
applying to.

**You do:** push to a private GitHub repo, then add two repository secrets under
Settings -> Secrets and variables -> Actions:

| Secret | Value |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT` | the entire contents of `service_account.json` |
| `SHEET_ID` | your spreadsheet id |

Or, with the `gh` CLI:

```bash
gh secret set GOOGLE_SERVICE_ACCOUNT < pipeline/service_account.json
gh secret set SHEET_ID --body "<your sheet id>"
gh workflow run daily.yml          # test it before trusting the schedule
```

Cost: one run is ~1 billed minute, so ~30 min/month against the 2000 free
private-repo minutes.

It runs at **01:00 UTC** on purpose. GitHub cron is UTC and never follows
daylight saving, and Actions schedules can lag by hours, so an overnight slot
leaves a long runway before you start work. It also matters that it lands while
you are asleep: `fetch.py` rewrites the Inbox tab wholesale, so a run firing
mid-review would clobber ticks you had just made.

---

## Making it yours

**`pipeline/profile.md`** is the file to edit. Everything else has a sensible
default. The yaml block is what the scorer matches on; the prose below it is for
you and for whatever assistant helps you write cover letters.

**`pipeline/config.yml`** holds every weight and threshold, all commented. The
shipped geography (Europe and the US first, then Canada / Australia / Singapore
/ Japan / Israel / Hong Kong) is one candidate's preference. Move a country
between the two lists to change it.

Scoring is four parts, added, max 50:

```
score = geography (12) + field (14) + role (12) + research match (12)
```

Every listing carries a **Why** column showing its own breakdown
(`geo:Ireland+12 | field:econ+14 | role:assistant+12 | match:tier1+8`), so a
score you disagree with can always be traced to the line that caused it.

**If you change a weight, re-check `bucket_cutoffs` against the new
distribution** using the block in `pipeline/PIPELINE.md`, or bucket A quietly
becomes everything.

## Tests

```bash
python3 -m pytest pipeline/test_pipeline.py -q
```

Every case is a bug that actually shipped during development, or the boundary
separating it from a correct call. The rules are pattern matching over free
text, so mistakes silently demote real jobs instead of crashing:

- `intern` matched inside "**Intern**ational" and demoted forty tenure-track jobs
- `\bfull\b` matched inside "**Full**-Time Academic", so every JOE academic ad
  looked bundled with a senior hire
- every uppercase token in a JOE location was swallowed into the country, so US
  jobs scored zero for geography
- `AI` as a substring matches "ch**ai**r" and "tr**ai**ning"

If you change a pattern, add a test, then reintroduce the bug and check it goes
red. A test that has never failed proves nothing; doing this found one of mine
that was blind.

## What it does not do

- **Coverage is JOE and EJM.** Together they are most of the market, but some
  European departments post only on their own pages, and Australian and Latin
  American listings are patchy on both.
- **It never decides for you.** It ranks and it remembers. Promoting is always
  a click you make.
- **It does not write applications.** It tells you what is out there and what
  you already sent.

## How this was built

Written with [Claude Code](https://claude.com/claude-code), in a single long
session, against the live 2026--27 market. `pipeline/PIPELINE.md` is the
engineering log: how each source is fetched, why the guards exist, and the bugs
that motivated them. It is worth reading before changing the triage.

## Licence

MIT. By [Niccolò Zaccaria](https://github.com/NZaccaria).
