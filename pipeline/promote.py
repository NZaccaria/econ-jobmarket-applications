#!/usr/bin/env python3
"""Act on your Inbox decisions.

Run:  python3 00_pipeline/promote.py [--dry-run]

Ticked   -> Applications tab, status "promoted". Never shown for review again.
Unticked -> Parked tab, status "parked". Out of the Inbox but not lost: tick a
            row on the Parked tab and the next run promotes it.

So every run empties the Inbox. Whatever appears there next is genuinely new
since you last reviewed, which is the point: you never re-read the same list.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import sheet as S  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    args = ap.parse_args()

    cfg = C.load_config()
    catalog = C.load_catalog(cfg)

    sh = C.open_sheet()
    apps, inbox = S.ensure_tabs(sh)
    inbox_ticks = S.read_ticks(inbox)
    parked_ticks = S.read_ticks(sh.worksheet(S.PARKED))
    if not inbox_ticks and not parked_ticks:
        print("Inbox is empty. Run fetch.py first.")
        return 0

    ticked = [u for u, on in inbox_ticks.items() if on]
    revived = [u for u, on in parked_ticks.items() if on]
    to_park = [u for u, on in inbox_ticks.items() if not on]

    already = S.existing_app_uids(apps)
    to_add = [u for u in ticked + revived if u not in already and u in catalog]

    # A collapsed twin never reaches the Inbox and cannot be ticked; this is a
    # guard in case a stale row is still sitting there.
    twins = [u for u in to_add if catalog[u].get("duplicate")]
    if twins:
        print(f"   skipping {len(twins)} rows already represented by their EJM twin")
        to_add = [u for u in to_add if u not in twins]

    records = []
    for u in to_add:
        r = dict(catalog[u])
        if r.get("also_on"):
            r["source"] = "JoE + EJM"
            r["bundled"] = f"{r['uid']}, {r['also_on']}"
        records.append(r)
    records.sort(key=lambda r: (r.get("deadline") or "9999", r.get("institution", "")))

    both = sum(1 for r in records if r.get("bundled"))
    print(f"   {len(to_add)} to add to Applications"
          + (f" ({len(revived)} revived from Parked)" if revived else ""))
    if both:
        print(f"   {both} of them are advertised on both sites; one row each")
    for r in records[:10]:
        print(f"     + [{r['bucket']}] {r['institution'][:32]:32} {r['title'][:36]:36} "
              f"dl {r['deadline'] or '-'}")
    if len(records) > 10:
        print(f"     ... and {len(records) - 10} more")
    print(f"   {len(to_park)} unticked rows will be parked")

    if args.dry_run:
        print("\n   dry run: nothing written")
        return 0

    added = S.append_applications(records) if records else 0
    for u in to_add:
        catalog[u]["status"] = C.PROMOTED
    for u in to_park:
        if u in catalog and catalog[u].get("status") == C.NEW:
            catalog[u]["status"] = C.PARKED
    C.save_catalog(cfg, catalog)

    # Redraw both tabs so the Inbox is empty and Parked reflects the new state.
    pending = [r for r in catalog.values() if r.get("status") == C.NEW]
    parked = [r for r in catalog.values() if r.get("status") == C.PARKED]
    S.push_inbox(cfg, pending, parked)
    S.stamp_last_updated(apps)

    print(f"\n   added {added} rows to Applications")
    print(f"   Inbox now {len(pending)}, Parked {len(parked)}")
    print("   next: fill Letter Writer columns, tick Applied when you submit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
