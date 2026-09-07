#!/usr/bin/env python3
"""Fetch listings, triage them, and update the catalog and the Inbox.

Run:  python3 00_pipeline/fetch.py [--no-sheet] [--dry-run]

Orchestration only: sources.py knows where listings come from, triage.py knows
what they are worth, sheet.py knows the spreadsheet.

Nothing is ever deleted. Every listing seen stays in openings.csv for good; the
triage decides ordering and which box starts ticked, never visibility.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import sources  # noqa: E402
import triage  # noqa: E402

# Re-exported so the sources and the rules stay reachable as fetch.<name>,
# which is how PIPELINE.md's audit snippets refer to them.
fetch_joe = sources.fetch_joe
fetch_ejm = sources.fetch_ejm
EJM_RA_LIST = sources.EJM_RA_LIST
triage_one = triage.triage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sheet", action="store_true", help="catalog only, skip Google Sheets")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    args = ap.parse_args()

    cfg = C.load_config()
    # Fail before spending 30 seconds fetching: a missing credential or sheet
    # id is the most likely first-run mistake, and finding out at the end is a
    # miserable way to learn it.
    if not args.no_sheet and not args.dry_run:
        C.open_sheet()
    state = C.load_state(cfg)
    catalog = C.load_catalog(cfg)

    fetched: list[dict] = []
    counts: dict[str, int] = {}
    for name, enabled, fn in (
        ("JoE", cfg["sources"]["joe"], sources.fetch_joe),
        ("EJM", cfg["sources"]["ejm"], sources.fetch_ejm),
        ("EJM-RA", cfg["sources"].get("ejm_ra", False),
         lambda: sources.fetch_ejm(sources.EJM_RA_LIST, "EJM-RA")),
    ):
        if not enabled:
            continue
        try:
            rows = fn()
        except Exception as exc:
            print(f"!! {name} fetch FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            counts[name] = -1
            continue
        counts[name] = len(rows)
        fetched.extend(rows)
        print(f"   {name}: {len(rows)} listings")

    # The guard against a quietly broken parser writing an empty catalogue.
    floor = cfg["min_fraction_of_last_run"]
    for name, n in counts.items():
        last = state.get("counts", {}).get(name, 0)
        if n < 0:
            print(f"!! {name} errored; keeping previous {last} rows untouched.", file=sys.stderr)
            return 2
        if last and n < last * floor:
            print(f"!! {name} returned {n}, was {last} last run (below {floor:.0%}). "
                  "Refusing to write. Check the parser.", file=sys.stderr)
            return 2

    today = C.today()
    new_uids, changed = [], 0
    for rec in fetched:
        rec = triage.triage(rec, cfg)
        full = rec.pop("_full_text", "")
        uid = rec["uid"]
        if uid in catalog:
            prev = catalog[uid]
            rec["status"] = prev.get("status", C.NEW)
            rec["first_seen"] = prev.get("first_seen", today)
            if prev.get("deadline") != rec["deadline"]:
                changed += 1
        else:
            rec["status"] = C.NEW
            rec["first_seen"] = today
            new_uids.append(uid)
            if full:
                (C.ads_dir(cfg) / f"{uid.replace(':', '_')}.txt").write_text(full, encoding="utf-8")
        rec["last_seen"] = today
        catalog[uid] = rec

    # The SHEET is the source of truth for decisions, not this file. A uid on the
    # Applications tab is promoted; one on Parked is parked. That way anything
    # that moves rows in the spreadsheet (the Apps Script button, or you by
    # hand) is respected, instead of being undone by the next fetch.
    if not args.no_sheet:
        import sheet
        decided = sheet.decisions()
        for uid, decision in decided.items():
            if uid in catalog:
                catalog[uid]["status"] = decision
        for r in catalog.values():
            if r["uid"] not in decided and r.get("status") in (C.PROMOTED, C.PARKED):
                # Removed from the sheet by hand: treat that as undecided again.
                r["status"] = C.NEW

    # Expire anything past its deadline. Kept in the catalog, dropped from the Inbox.
    if cfg["drop_expired"]:
        for r in catalog.values():
            if r.get("status") == C.NEW and r.get("deadline") and r["deadline"] < today:
                r["status"] = C.EXPIRED

    dupes, singles = triage.collapse_cross_posts(catalog, cfg)
    # Collapsed twins keep status "new" on purpose: if a later run stops judging
    # them a duplicate, they reappear for review. They are simply not counted
    # as pending, because they are never shown.
    pending = [r for r in catalog.values()
               if r.get("status") == C.NEW and not r.get("duplicate")]
    parked = [r for r in catalog.values() if r.get("status") == C.PARKED]
    print(f"\n   {len(new_uids)} new, {changed} deadline changes, "
          f"{len(pending)} pending review, {len(catalog)} in catalog")
    print(f"   {dupes} openings collapsed (on both JoE and EJM), {singles} single-site")
    by_bucket: dict[str, int] = {}
    for r in pending:
        by_bucket[r["bucket"]] = by_bucket.get(r["bucket"], 0) + 1
    print("   pending by bucket: " + ", ".join(f"{k}={v}" for k, v in sorted(by_bucket.items())))

    if args.dry_run:
        print("\n   dry run: nothing written")
        return 0

    C.save_catalog(cfg, catalog)
    state["counts"] = {k: v for k, v in counts.items()}
    state["last_run"] = today
    C.save_state(cfg, state)

    if not args.no_sheet:
        import sheet
        sheet.push_inbox(cfg, pending, parked)
        print(f"   Inbox updated ({len(pending)} rows), Parked ({len(parked)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
