"""Shared helpers: config, paths, Google Sheets access, catalog I/O."""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
KEY_FILE = HERE / "service_account.json"


def sheet_id() -> str:
    """The spreadsheet to work on.

    Read from config.yml, or the SHEET_ID environment variable, so the code can
    be shared without carrying anyone's personal tracker id.
    """
    import os
    env = os.environ.get("SHEET_ID")
    if env:
        return env
    sid = load_config().get("sheet_id")
    if not sid or sid.startswith("PUT_YOUR"):
        sys.exit(
            "No sheet_id set.\n"
            "  Put your spreadsheet id in config.yml under sheet_id, or set the\n"
            "  SHEET_ID environment variable. Take it from the sheet's URL:\n"
            "  docs.google.com/spreadsheets/d/<THIS PART>/edit\n"
            "  To work without Google at all, add --no-sheet."
        )
    return sid

# Order matters: this is the column order of openings.csv.
FIELDS = [
    "uid", "source", "institution", "department", "title", "section",
    "category", "rank_hint", "fields", "jel", "city", "country",
    "deadline", "posted", "letters_required", "url",
    "score", "score_why", "bucket", "skip_reason", "duplicate", "also_on",
    "status", "first_seen", "last_seen",
]

# status values
NEW, PROMOTED, PARKED, EXPIRED = "new", "promoted", "parked", "expired"


def load_config() -> dict:
    with open(HERE / "config.yml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_PROFILE_CACHE: dict | None = None


def load_profile() -> dict:
    """Research tiers from 00_pipeline/profile.md.

    The keywords live in profile.md rather than config.yml so there is one
    visible, editable place describing what the candidate works on. The file is
    also read by the tailor-cover-letter skill.
    """
    global _PROFILE_CACHE
    if _PROFILE_CACHE is not None:
        return _PROFILE_CACHE
    path = HERE / "profile.md"
    if not path.exists():
        raise SystemExit(f"Missing {path}. It holds the research keywords used for scoring.")
    text = path.read_text(encoding="utf-8")
    m = re.search(r"```yaml\n(.*?)```", text, re.S)
    if not m:
        raise SystemExit(
            f"No ```yaml block found in {path}. The scorer reads its tiers from it."
        )
    data = yaml.safe_load(m.group(1)) or {}
    for tier in ("tier1", "tier2", "tier3"):
        data.setdefault(tier, {"terms": [], "jel": []})
        data[tier].setdefault("terms", [])
        data[tier].setdefault("jel", [])
    _PROFILE_CACHE = data
    return data


def term_matches(term: str, haystack: str) -> bool:
    """Whole-word, case-insensitive. Short terms are the reason this exists:
    a plain substring test makes "AI" match "chair" and "training"."""
    return re.search(rf"\b{re.escape(term)}\b", haystack, re.I) is not None


def catalog_path(cfg) -> Path:
    return HERE / cfg["paths"]["catalog"]


def ads_dir(cfg) -> Path:
    d = HERE / cfg["paths"]["ads"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path(cfg) -> Path:
    return HERE / cfg["paths"]["state"]


def load_catalog(cfg) -> dict[str, dict]:
    """Existing catalog keyed by uid. Missing file is an empty catalog."""
    path = catalog_path(cfg)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["uid"]: r for r in csv.DictReader(fh)}


def save_catalog(cfg, rows: dict[str, dict]) -> None:
    """Write atomically: a crash mid-write must not truncate the catalog."""
    path = catalog_path(cfg)
    tmp = path.with_suffix(".csv.tmp")
    ordered = sorted(rows.values(), key=lambda r: (r.get("first_seen", ""), r["uid"]))
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(ordered)
    tmp.replace(path)


def load_state(cfg) -> dict:
    path = state_path(cfg)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(cfg, state: dict) -> None:
    state_path(cfg).write_text(json.dumps(state, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# Google Sheets
# --------------------------------------------------------------------------

_SHEET_CACHE = None


def open_sheet():
    """Authorised handle on the spreadsheet, cached for the process.

    Cached because a single run opens it more than once, and each call is a
    fresh OAuth exchange plus an open-by-key round trip.
    """
    global _SHEET_CACHE
    if _SHEET_CACHE is not None:
        return _SHEET_CACHE
    import gspread
    from google.oauth2.service_account import Credentials

    key = KEY_FILE
    if not key.exists():
        env = json.loads(_env_key()) if _env_key() else None
        if env is None:
            sys.exit(
                f"No Google credentials found.\n"
                f"  Expected {key.name} in {key.parent}, or the "
                f"GOOGLE_SERVICE_ACCOUNT environment variable (used by CI).\n"
                f"  To work without Google at all, run:  "
                f"python3 {key.parent.name}/fetch.py --no-sheet\n"
                f"  Setup instructions are in the README, Level 1."
            )
        creds = Credentials.from_service_account_info(
            env, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    else:
        creds = Credentials.from_service_account_file(
            str(key), scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    _SHEET_CACHE = gspread.authorize(creds).open_by_key(sheet_id())
    return _SHEET_CACHE


def _env_key():
    import os
    return os.environ.get("GOOGLE_SERVICE_ACCOUNT")


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------

def clean(text) -> str:
    """Collapse whitespace. Pandas empty cells arrive as the float nan, whose
    str() is the literal "nan"; that must not reach the spreadsheet."""
    if text is None:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    return "" if s.lower() in {"nan", "nat", "none", "<na>"} else s


def parse_date(value) -> str:
    """Return ISO yyyy-mm-dd, or '' when the source gave nothing usable."""
    if value is None:
        return ""
    s = clean(value)
    if not s or s.lower() in {"nan", "nat", "none"}:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d %b %Y", "%d %B %Y",
                "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def today() -> str:
    return date.today().isoformat()


