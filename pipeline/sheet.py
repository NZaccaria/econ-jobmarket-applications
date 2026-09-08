"""Google Sheets I/O: the Inbox tab you tick, and the Applications tracker."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

BUCKET_ORDER = {"A": 0, "B": 1, "C": 2, "skip": 3}

# Lifted from the Tilburg template so our sheet looks like the original.
ORANGE = {"red": 0.95686275, "green": 0.39607844, "blue": 0.14117648}
PEACH = {"red": 1, "green": 0.9019608, "blue": 0.8666667}
WHITE = {"red": 1, "green": 1, "blue": 1}

LINK_BLUE = {"red": 0.06666667, "green": 0.33333334, "blue": 0.8}

INBOX = "Inbox"
PARKED = "Parked"
APPS = "Applications"

# Columns are addressed BY NAME everywhere below, never by position. The
# spreadsheet button (AppsScript.gs) does the same, and a test asserts the two
# agree. Hardcoded indexes were how an earlier version could silently write the
# wrong field into the wrong column after a header was added.
INBOX_HEADERS = [
    "Apply?", "Bucket", "Score", "Why", "Source", "Institution", "Department",
    "Position", "Fields", "City", "Country", "Deadline", "Letters",
    "Link", "Why skipped", "Both sites", "Added", "uid",
]

# The Tilburg template's own columns, row 2 of the Applications tab.
APP_HEADERS = [
    "Applied", "Interview", "Flyout", "Offer", "Institution", "City",
    "Department", "Position", "Field", "Deadline", "Platform",
    "Application method", "Application URL", "Application email",
    "Description", "Letter Writer 1", "Letter Writer 2", "Letter Writer 3",
    "Letter Writer 4", "Notes", "Signal JOE", "Signal EJME", "uid",
]


# Every logical column on the Applications tab: these get real tickboxes,
# never a typed TRUE/FALSE.
APP_TICKBOXES = ["Applied", "Interview", "Flyout", "Offer",
                 "Letter Writer 1", "Letter Writer 2", "Letter Writer 3",
                 "Letter Writer 4", "Signal JOE", "Signal EJME"]


def col(headers: list[str], name: str) -> int:
    """Zero-based index of a column, by header name."""
    return headers.index(name)


def a1(index0: int, row: int) -> str:
    """Zero-based column index to an A1 reference, e.g. (22, 2) -> 'W2'."""
    n, letters = index0 + 1, ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def row_from(headers: list[str], values: dict) -> list:
    """Build a row in header order from a {header name: value} mapping.

    Adding a column to the header list therefore cannot shift existing data
    into the wrong place; at worst the new column comes out blank.
    """
    return [values.get(h, "") for h in headers]


# --------------------------------------------------------------------------

def ensure_tabs(sh):
    """Make sure the three tabs exist and Applications has its header row.

    Written to work on a brand-new empty spreadsheet, which is how anyone else
    starts. A new sheet's single default tab is called "Sheet1" only in an
    English locale ("Foglio1", "Hoja 1", ...), so the tab is adopted by being
    the only one present rather than by its name.

    Headers are only written when they are absent, so an existing tracker is
    never overwritten.
    """
    tabs = sh.worksheets()
    titles = [ws.title for ws in tabs]

    if APPS not in titles:
        if len(tabs) == 1 and titles[0] not in (INBOX, PARKED):
            tabs[0].update_title(APPS)          # adopt the default empty tab
        else:
            sh.add_worksheet(title=APPS, rows=500, cols=len(APP_HEADERS) + 6)

    apps = sh.worksheet(APPS)
    header_row = apps.row_values(2)
    if "Institution" not in header_row or "uid" not in header_row:
        # Blank tab, or one predating the uid column. Writing the full row is
        # safe here precisely because we only reach it when it is not a tracker.
        apps.update(values=[APP_HEADERS], range_name="A2")
        apps.update(values=[["Last updated:"]], range_name="A1")
        # Style it now rather than at the first promote, so a freshly set up
        # sheet does not look broken until you have applied to something.
        format_applications(sh, apps, 0)

    for tab in (INBOX, PARKED):
        if tab not in titles:
            sh.add_worksheet(title=tab, rows=1000, cols=len(INBOX_HEADERS) + 2)
    return sh.worksheet(APPS), sh.worksheet(INBOX)


# --------------------------------------------------------------------------

def read_ticks(inbox) -> dict[str, bool]:
    """uid -> ticked, from whatever is currently in the Inbox tab."""
    vals = inbox.get_all_values()
    if not vals:
        return {}
    head = vals[0]
    try:
        u = head.index("uid")
        tick = head.index("Apply?")
    except ValueError:
        return {}
    out = {}
    for r in vals[1:]:
        if len(r) > u and C.clean(r[u]):
            out[C.clean(r[u])] = len(r) > tick and C.clean(r[tick]).upper() == "TRUE"
    return out


def push_inbox(cfg, pending: list[dict], parked: list[dict] | None = None,
               note: str = "") -> None:
    """Rewrite the Inbox, and the Parked tab when parked rows are supplied."""
    sh = C.open_sheet()
    _, inbox = ensure_tabs(sh)
    _write_rows(sh, inbox, pending, default_tick=True, note=note)
    if parked is not None:
        _write_rows(sh, sh.worksheet(PARKED), parked, default_tick=False)


def _write_rows(sh, ws, pending: list[dict], default_tick: bool,
                note: str = "") -> None:
    previous = read_ticks(ws)

    # The collapsed twin is not shown: its opening is represented by the
    # surviving row, which is flagged "also on JoE". Both stay in openings.csv.
    pending = [r for r in pending if not r.get("duplicate")]
    rows = sorted(
        pending,
        key=lambda r: (BUCKET_ORDER.get(r.get("bucket", "C"), 9),
                       -int(r.get("score") or 0),
                       r.get("deadline") or "9999"),
    )

    body = []
    for r in rows:
        uid = r["uid"]
        # A tick you already made always wins. Otherwise pre-tick everything
        # that is not a wrong kind of post, per the "default is promote" rule.
        # On the Parked tab nothing is pre-ticked: a tick there means "actually,
        # bring this back", which promote.py picks up on its next run.
        ticked = previous.get(uid, default_tick and r.get("bucket") != "skip")
        other = r.get("also_on", "")
        body.append(row_from(INBOX_HEADERS, {
            "Apply?": "TRUE" if ticked else "FALSE",
            "Bucket": r.get("bucket", ""), "Score": r.get("score", ""),
            "Why": r.get("score_why", ""), "Source": r.get("source", ""),
            "Institution": r.get("institution", ""),
            "Department": r.get("department", ""), "Position": r.get("title", ""),
            "Fields": r.get("fields", "")[:120], "City": r.get("city", ""),
            "Country": r.get("country", ""), "Deadline": r.get("deadline", ""),
            "Letters": r.get("letters_required", ""), "Link": r.get("url", ""),
            "Why skipped": r.get("skip_reason", ""),
            "Both sites": f"also on JoE ({other})" if other else "",
            "Added": r.get("first_seen", ""), "uid": uid,
        }))

    # An empty Inbox is ambiguous: nothing new, or the job never ran? Say so
    # in the tab itself, since that is the only place the answer is looked for.
    placeholder = not body and note
    if placeholder:
        body = [row_from(INBOX_HEADERS, {"Institution": note})]

    ws.clear()
    ws.update(values=[INBOX_HEADERS] + body, range_name="A1",
              value_input_option="USER_ENTERED")
    # n_rows 0 for a placeholder: it must not get a tickbox, and it carries no
    # uid so read_ticks and the Apps Script both ignore it.
    _format_inbox(sh, ws, 0 if placeholder else len(body))


def _format_inbox(sh, inbox, n_rows: int) -> None:
    """Real checkboxes in column A, frozen header, sensible widths."""
    sid = inbox.id
    reqs = _drop_banding(sh, inbox)
    reqs.append(_banding(inbox, 0, max(n_rows + 1, 2)))
    if n_rows:
        # Only add checkboxes where there are rows. Forcing a minimum of one
        # leaves a stray ticked-looking cell on an empty tab.
        reqs.append({"setDataValidation": {
            "range": {"sheetId": sid, "startRowIndex": 1,
                      "endRowIndex": n_rows + 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True}}})
    reqs += [
        {"updateSheetProperties": {
            "properties": {"sheetId": sid,
                           "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": 11}}},
            "fields": "userEnteredFormat.textFormat"}},
    ]
    if n_rows:
        # Institution bold, matching the Applications tab.
        reqs.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": n_rows + 1,
                      "startColumnIndex": col(INBOX_HEADERS, "Institution"),
                      "endColumnIndex": col(INBOX_HEADERS, "Institution") + 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 10}}},
            "fields": "userEnteredFormat.textFormat"}})
        reqs.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": n_rows + 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.horizontalAlignment"}})
    widths = {"Apply?": 70, "Bucket": 60, "Score": 55, "Why": 260,
              "Source": 70, "Institution": 220, "Department": 180,
              "Position": 240, "Fields": 200, "Deadline": 90}
    for name, width in widths.items():
        idx = col(INBOX_HEADERS, name)
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": idx, "endIndex": idx + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize"}})
    sh.batch_update({"requests": reqs})


# --------------------------------------------------------------------------

def _drop_banding(sh, ws) -> list[dict]:
    """Banded ranges cannot overlap, so existing ones must go before adding."""
    meta = sh.fetch_sheet_metadata()
    out = []
    for s in meta.get("sheets", []):
        if s["properties"]["sheetId"] != ws.id:
            continue
        for b in s.get("bandedRanges", []):
            out.append({"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}})
    return out


def _banding(ws, header_row: int, last_row: int) -> dict:
    """Orange header then alternating white / peach, as in the template."""
    return {"addBanding": {"bandedRange": {
        "range": {"sheetId": ws.id, "startRowIndex": header_row,
                  "endRowIndex": last_row, "startColumnIndex": 0,
                  "endColumnIndex": 29},
        "rowProperties": {"headerColorStyle": {"rgbColor": ORANGE},
                          "firstBandColorStyle": {"rgbColor": WHITE},
                          "secondBandColorStyle": {"rgbColor": PEACH}}}}}


def format_applications(sh, apps, n_rows: int) -> None:
    """Reproduce the Tilburg template's look on the Applications tab."""
    sid = apps.id
    last = max(n_rows + 2, 3)
    reqs = _drop_banding(sh, apps)
    reqs.append(_banding(apps, 1, max(last, 204)))
    # Header row bold, 11pt.
    reqs.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2},
        "cell": {"userEnteredFormat": {
            "textFormat": {"bold": True, "fontSize": 11},
            "horizontalAlignment": "LEFT"}},
        "fields": "userEnteredFormat(textFormat,horizontalAlignment)"}})
    if n_rows:
        # Body 10pt, then institution bold, then the tickbox columns centred.
        reqs.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": last},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": False, "fontSize": 10},
                "horizontalAlignment": "LEFT"}},
            "fields": "userEnteredFormat(textFormat,horizontalAlignment)"}})
        reqs.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": last,
                      "startColumnIndex": col(APP_HEADERS, "Institution"),
                      "endColumnIndex": col(APP_HEADERS, "Institution") + 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 10}}},
            "fields": "userEnteredFormat.textFormat"}})
        for name in APP_TICKBOXES:
            idx = col(APP_HEADERS, name)
            rng = {"sheetId": sid, "startRowIndex": 2, "endRowIndex": last,
                   "startColumnIndex": idx, "endColumnIndex": idx + 1}
            reqs.append({"setDataValidation": {
                "range": rng,
                "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True}}})
            reqs.append({"repeatCell": {
                "range": rng,
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment"}})
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 2}},
        "fields": "gridProperties.frozenRowCount"}})
    app_widths = {"Institution": 220, "Department": 170, "Position": 230,
                  "Field": 150, "Application URL": 90, "Notes": 200}
    for name, width in app_widths.items():
        idx = col(APP_HEADERS, name)
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": idx, "endIndex": idx + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize"}})
    reqs += _link_url_column(apps, n_rows)
    sh.batch_update({"requests": reqs})


def _link_url_column(apps, n_rows: int) -> list[dict]:
    """Turn the Application URL column into real clickable links.

    The template stores a plain string carrying a hyperlink, blue and
    underlined, rather than a HYPERLINK() formula, so the cell still reads as a
    URL if you copy it out. Written as one updateCells request with one row per
    listing, because each cell needs its own uri.
    """
    if not n_rows:
        return []
    url_col = col(APP_HEADERS, "Application URL")
    urls = apps.col_values(url_col + 1)[2:2 + n_rows]
    rows = []
    for u in urls:
        u = (u or "").strip()
        if not u.startswith("http"):
            rows.append({"values": [{}]})
            continue
        rows.append({"values": [{
            "userEnteredValue": {"stringValue": u},
            "userEnteredFormat": {"textFormat": {
                "link": {"uri": u}, "foregroundColor": LINK_BLUE,
                "underline": True, "fontSize": 10}}}]})
    return [{"updateCells": {
        "range": {"sheetId": apps.id, "startRowIndex": 2,
                  "endRowIndex": 2 + len(rows),
                  "startColumnIndex": url_col, "endColumnIndex": url_col + 1},
        "rows": rows,
        "fields": "userEnteredValue,userEnteredFormat.textFormat"}}]


def decisions() -> dict[str, str]:
    """uid -> "promoted" | "parked", read from the spreadsheet.

    The sheet is authoritative for decisions so that moving rows there, whether
    by the Apps Script button or by hand, is respected by the next fetch rather
    than reverted.
    """
    sh = C.open_sheet()
    apps, _ = ensure_tabs(sh)
    out: dict[str, str] = {}
    for uid in existing_app_uids(apps):
        out[uid] = C.PROMOTED
    parked = sh.worksheet(PARKED)
    vals = parked.get_all_values()
    if vals:
        try:
            u = vals[0].index("uid")
        except ValueError:
            return out
        for r in vals[1:]:
            if len(r) > u and C.clean(r[u]):
                out.setdefault(C.clean(r[u]), C.PARKED)
    return out


def existing_app_uids(apps) -> set[str]:
    vals = apps.get_all_values()
    if len(vals) < 2:
        return set()
    header = vals[1]
    try:
        u = header.index("uid")
    except ValueError:
        return set()
    return {C.clean(r[u]) for r in vals[2:] if len(r) > u and C.clean(r[u])}


def append_applications(records: list[dict]) -> int:
    """Add promoted listings to the Applications tab. Skips anything already there."""
    sh = C.open_sheet()
    apps, _ = ensure_tabs(sh)
    have = existing_app_uids(apps)

    body = []
    for r in records:
        if r["uid"] in have:
            continue
        both = r.get("bundled")
        body.append(row_from(APP_HEADERS, {
            "Applied": "FALSE", "Interview": "FALSE",
            "Flyout": "FALSE", "Offer": "FALSE",
            "Institution": r.get("institution", ""), "City": r.get("city", ""),
            "Department": r.get("department", ""), "Position": r.get("title", ""),
            "Field": r.get("fields", "")[:120], "Deadline": r.get("deadline", ""),
            "Platform": r.get("source", ""),
            "Application method": r.get("source", ""),
            "Application URL": r.get("url", ""),
            "Application email": "",
            # Description carries the pipeline's own provenance.
            # Notes is left empty on purpose: that column is yours to write in.
            "Description": (f"bucket {r.get('bucket')} · score {r.get('score')}"
                            + (f" · listed on both sites: {both}" if both else "")),
            "Letter Writer 1": "FALSE", "Letter Writer 2": "FALSE",
            "Letter Writer 3": "FALSE", "Letter Writer 4": "FALSE",
            "Notes": "",
            "Signal JOE": "FALSE", "Signal EJME": "FALSE",
            "uid": r["uid"],
        }))
    if body:
        apps.append_rows(body, value_input_option="USER_ENTERED",
                         table_range="A2")
    total = len(apps.get_all_values()) - 2
    format_applications(sh, apps, max(total, 0))
    return len(body)


def stamp_last_updated(apps, note: str = "") -> None:
    """Cell B1 of the tracker: when the pipeline last ran, and what it found.

    This is how you answer "did the nightly job work?" without leaving the
    spreadsheet, which is the only place you actually work.
    """
    text = C.today() + (f"  ·  {note}" if note else "")
    apps.update(values=[[text]], range_name="B1", value_input_option="USER_ENTERED")
