# econ-jobmarket-applications

Finds economics job openings on **JOE** and **EconJobMarket**, ranks them
against your research, and tracks what you applied to in a Google Sheet.

Once set up it runs itself every night. New openings appear in an **Inbox** tab.
You tick the ones you want and press a button in the spreadsheet; they move to
an **Applications** tab, which is your record of where you applied.

Built for a market where you send hundreds of applications.

## Files you edit

Two, and only during setup.

| File | What you put in it |
|---|---|
| `pipeline/profile.md` | your research: the fields and JEL codes that should rank highly |
| `pipeline/config.yml` | your spreadsheet id, and optionally the scoring weights |

Everything else is the program. You never edit it.

---

# Setup

Eight steps, in order. Steps 4 to 7 need a browser and only you can do them.
The whole thing takes about 20 minutes.

## 1. Install

```bash
git clone https://github.com/NZaccaria/econ-jobmarket-applications
cd econ-jobmarket-applications
pip install -r pipeline/requirements.txt
```

## 2. Describe your research

Open `pipeline/profile.md`. Near the top is a `yaml` block with three tiers.
Replace them with your own fields and JEL codes. The file shipped here belongs
to a fictional labour economist, so leaving it alone will rank badly for you.

Use words a hiring committee actually writes in an ad. "Artificial
intelligence", not the title of your paper.

## 3. Check it works

```bash
python3 pipeline/fetch.py --no-sheet
```

This downloads every current opening and writes `pipeline/openings.csv`, scored
and sorted. Open it in Excel and look at the `score_why` column to see why
things ranked where they did.

Nothing has been set up yet: no accounts, no spreadsheet. This step exists so
you can see the ranking and fix `profile.md` before going further. If the top of
that list looks wrong, go back to step 2.

**If a spreadsheet is more than you need, you can stop here** and just re-run
this command whenever you want an updated list.

## 4. Create the spreadsheet

Make a new, blank Google Sheet. The program creates the tabs itself.

From its URL, copy the id:
`docs.google.com/spreadsheets/d/`**`THIS-PART`**`/edit`

Paste it into `pipeline/config.yml`, replacing `PUT_YOUR_SHEET_ID_HERE`.

## 5. Create a Google service account

A service account is a robot Google account with its own email address. The
program signs in as it, which is what lets the nightly run work while you are
asleep.

1. Go to <https://console.cloud.google.com> and create a project. Any name.
2. Enable the Sheets API:
   <https://console.cloud.google.com/apis/library/sheets.googleapis.com> ->
   **Enable**. Only this one.
3. **Credentials** -> **Create credentials** -> **Service account**. Give it a
   name, **Create**, **Done**.
4. Click it, then **Keys** -> **Add key** -> **Create new key** -> **JSON**.
   A file downloads.
5. Save that file as `pipeline/service_account.json`.

## 6. Give the robot access to your sheet

Copy the service account's email address. It looks like
`name@your-project.iam.gserviceaccount.com`.

In your Google Sheet: **Share**, paste that address, set it to **Editor**, Send.
Ignore the warning that it looks like a robot account. It is one.

Without this step the program can see nothing: the account exists but has not
been invited to your sheet.

## 7. Build the tabs

```bash
python3 pipeline/fetch.py
```

Same as step 3, except it now also fills the spreadsheet. It creates three tabs:

- **Inbox** — openings you have not decided on yet
- **Parked** — ones you said no to
- **Applications** — ones you are applying to

Look at the Inbox. Every row has a tickbox in the first column.

## 8. Add the button

So that you can promote rows from the spreadsheet instead of the command line.

In your sheet: **Extensions** -> **Apps Script**. Delete what is in `Code.gs`,
paste in the contents of `pipeline/AppsScript.gs`, **Save**, then reload the
sheet. A **Job Market** menu appears next to Help. The first click asks for
authorisation, which is Google asking whether your own script may edit your own
sheet.

Setup is done.

---

# Using it

## Every day

Rows arrive in the **Inbox** already ticked, except kinds of post that are
wrong for a PhD candidate (pre-doc, adjunct, PhD student, senior-only chairs),
which arrive unticked.

1. Open the Inbox, on a laptop or the Google Sheets phone app.
2. Untick anything you do not want. Tick anything unticked that you do want.
3. **Job Market -> Promote ticked rows.**

Ticked rows move to **Applications**. Everything else moves to **Parked**. The
Inbox is now empty, so next time it contains only openings you have not seen.

In **Applications**, tick `Applied` yourself when you actually submit, and fill
in the letter writer columns.

Changed your mind about something parked? Tick it on the **Parked** tab and
press the button again.

## Getting new openings

Someone has to re-run the fetch to pick up new postings. Two ways:

**By hand.** Run `python3 pipeline/fetch.py` when you sit down to work. New
listings appear in the Inbox.

**Automatically**, using the included GitHub Action, in which case you never
touch a terminal again after setup. Push this repo to GitHub — **private**,
because it will contain which jobs you are applying to — and add two secrets
under Settings -> Secrets and variables -> Actions:

| Secret | Value |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT` | the whole contents of `service_account.json` |
| `SHEET_ID` | your spreadsheet id |

Or from the command line:

```bash
gh secret set GOOGLE_SERVICE_ACCOUNT < pipeline/service_account.json
gh secret set SHEET_ID --body "<your sheet id>"
gh workflow run daily.yml     # run it once now, to check it works
```

It then runs nightly at 01:00 UTC. One run costs about 1 minute of the 2000
free monthly minutes GitHub gives private repositories.

It runs overnight deliberately: the fetch rewrites the Inbox tab, so a run
starting while you are reviewing could wipe ticks you just made.

---

# How the ranking works

Four parts, added together, out of 50:

```
score = geography (12) + field (14) + role (12) + research match (12)
```

- **geography** — Europe and the US first, then Canada, Australia, Singapore,
  Japan, Israel, Hong Kong
- **field** — is it an economics department, as opposed to finance or business
- **role** — assistant professor, postdoc, open rank, policy economist
- **research match** — your `profile.md` tiers, best tier only

Every row shows its own breakdown in the **Why** column, for example
`geo:Ireland+12 | field:econ+14 | role:assistant+12 | match:tier1+8`, so a
score you disagree with can be traced to the line that caused it.

**The score only sorts. It never hides anything.** Missing an opening costs you
a job; an extra row costs you a glance. Your field never excludes a listing
either, only the kind of post does.

To change the weights, edit `scoring` in `pipeline/config.yml`. Everything is
commented. If you change a weight, re-check `bucket_cutoffs` against the new
distribution using the snippet in `pipeline/PIPELINE.md`.

# Tests

```bash
python3 -m pytest pipeline/test_pipeline.py -q
```

Every case is a bug that actually shipped while this was being written. The
rules are pattern matching over free text, so mistakes silently demote real jobs
rather than crashing: `intern` once matched inside "**Intern**ational" and
demoted forty tenure-track jobs. If you change a pattern, add a test.

# Limitations

- Covers JOE and EconJobMarket. Together they are most of the market, but some
  European departments post only on their own pages, and Australian and Latin
  American listings are patchy on both.
- It ranks and remembers. It never applies for you, and never decides for you.

# Notes

`pipeline/service_account.json` is a credential and is gitignored. If one ever
reaches a public repository, deleting the file is not enough: rotate the key in
Google Cloud, because the old copy stays in git history.

`pipeline/PIPELINE.md` is the engineering log: how each source is fetched, why
the guards exist, and the bugs that motivated them. Read it before changing the
triage.

# Licence

MIT. By [Niccolò Zaccaria](https://github.com/NZaccaria).
Written with [Claude Code](https://claude.com/claude-code).
