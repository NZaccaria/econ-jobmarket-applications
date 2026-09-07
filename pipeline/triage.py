"""What a listing is worth: category, score, and cross-posting.

Pure functions over listing dicts. No network and no spreadsheet, which is what
makes test_pipeline.py able to cover the rules that actually bite.

The recurring hazard here is pattern matching a string whose structure was
assumed rather than checked. Three bugs of that shape shipped during
development: `intern` matching inside "International", `\bfull\b` matching
inside "Full-Time Academic", and every uppercase token in a JOE location being
swallowed into the country name. Each silently demoted real jobs. Add a test
before changing a pattern.
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

def categorise(rec: dict, cfg: dict) -> str:
    """Which kind of post this is. Never about field, only about the kind of job.

    Tested against the title, plus EJM's category column (a real taxonomy).
    JOE's jp_section is NOT included: it is a shelf label like "Other Nonacademic
    (Temporary, Part-Time, ...)" whose words would otherwise mislabel real jobs.
    """
    hay = rec["title"]
    if rec["source"] == "EJM":
        hay += " " + rec["section"]
    hay = hay.lower()

    # JOE states adjunct status in its own section field, and there it is reliable.
    if rec["source"] == "JoE" and "part-time or adjunct" in rec["section"].lower():
        return "adjunct"

    # Senior-only needs the whole title inspected in both directions.
    if any(re.search(p, hay, re.I) for p in cfg["senior_terms"]) and \
       not any(re.search(p, hay, re.I) for p in cfg["junior_terms"]):
        return "senior_only"

    for cat, patterns in cfg["category_patterns"].items():
        for pat in patterns:
            if re.search(pat, hay, re.I):
                return cat
    return "other"


def section_bucket(rec: dict, category: str) -> str:
    s = rec["section"].lower()
    if "part-time" in s or "adjunct" in s:
        return "other"
    if "full-time academic" in s:
        return "academic_permanent"
    if "other academic" in s:
        return "academic_temporary"
    if "nonacademic" in s:
        return "nonacademic"
    if category == "faculty":
        return "academic_permanent"
    if category == "postdoc":
        return "postdoc"
    if category == "economist":
        return "nonacademic"
    return "other"


def geo_points(rec: dict, cfg: dict) -> tuple[int, str]:
    """Search the whole location string for a known country name.

    Exact-matching a parsed country field is too brittle: JOE location strings
    carry state and city names, and some ads list two countries. Searching means
    a job advertised in both Germany and the US still scores as priority.
    """
    g = cfg["scoring"]["geography"]
    hay = f"{rec.get('country', '')} {rec.get('city', '')}"
    if not C.clean(hay):
        return 0, "geo:?+0"
    for name in g["priority_countries"]:
        if C.term_matches(name, hay):
            return g["priority"], f"geo:{name}+{g['priority']}"
    for name in g["secondary_countries"]:
        if C.term_matches(name, hay):
            return g["secondary"], f"geo:{name}+{g['secondary']}"
    shown = C.clean(rec.get("country", "")) or "?"
    return g["rest"], f"geo:{shown}+{g['rest']}"


def field_points(rec: dict, cfg: dict) -> tuple[int, str]:
    """Is this actually an economics post.

    Department and title decide it when they say anything at all. The ad's own
    field list is used ONLY when they are silent, because a department name is
    honest and a field list is marketing: HKUST's "Financial Technology"
    department advertises macro and behavioural among its fields and is still a
    fintech job. But "MIT FutureTech" names no discipline, and there the field
    list ("Economics of AI") is the only signal there is.
    """
    f = cfg["scoring"]["field"]
    hay = f"{rec.get('department', '')} {rec.get('title', '')}".lower()
    if any(re.search(p, hay, re.I) for p in f["economics_terms"]):
        return f["economics"], f"field:econ+{f['economics']}"
    if any(re.search(p, hay, re.I) for p in f["other_terms"]):
        return f["other"], "field:non-econ+0"
    if any(re.search(p, hay, re.I) for p in f["adjacent_terms"]):
        return f["adjacent"], f"field:adjacent+{f['adjacent']}"

    # Department and title said nothing. Fall back to the advertised fields.
    fallback = rec.get("fields", "").lower()
    if any(re.search(p, fallback, re.I) for p in f["economics_terms"]):
        return f["economics"], f"field:econ(fields)+{f['economics']}"
    if any(re.search(p, fallback, re.I) for p in f["adjacent_terms"]):
        return f["adjacent"], f"field:adjacent(fields)+{f['adjacent']}"
    return f["other"], "field:other+0"


def role_points(rec: dict, cfg: dict, category: str) -> tuple[int, str]:
    r = cfg["scoring"]["role"]
    # Title only for JOE. Its jp_section reads "US: Full-Time Academic (...)",
    # and \bfull\b matches inside "Full-Time", which made every JOE academic ad
    # look like it was bundled with a full professorship. EJM's section really
    # is a rank list ("Assistant Professor • Associate Professor"), so it counts.
    hay = rec.get("title", "")
    if rec.get("source", "").startswith("EJM"):
        hay += " " + rec.get("section", "")
    hay = hay.lower()
    has_junior = bool(re.search(r"\bassistant\b", hay))
    has_senior = bool(re.search(r"\b(associate|full|chair)\b", hay))
    if category == "postdoc":
        return r["postdoc"], f"role:postdoc+{r['postdoc']}"
    if has_junior and has_senior:
        return r["open_rank"], f"role:open-rank+{r['open_rank']}"
    if has_junior:
        return r["assistant"], f"role:assistant+{r['assistant']}"
    if category == "economist":
        return r["economist"], f"role:economist+{r['economist']}"
    if category == "faculty" and not has_senior:
        return r["assistant"], f"role:faculty+{r['assistant']}"
    return r["other"], "role:other+0"


def match_points(rec: dict, cfg: dict) -> tuple[int, str]:
    """Alignment with profile.md. Best tier only, never stacked.

    JOE ads carry JEL codes, so those are matched first. EJM ads carry only
    free text, so the tier term lists are matched against the ad's field list
    and title, on whole words.
    """
    m = cfg["scoring"]["match"]
    profile = C.load_profile()
    jel = rec["jel"].split()
    hay = f"{rec.get('fields', '')} {rec.get('title', '')} {rec.get('department', '')}"

    best, label = 0, ""
    for tier in ("tier1", "tier2", "tier3"):
        codes = profile[tier]["jel"]
        terms = profile[tier]["terms"]
        if (jel and any(code in codes for code in jel)) or \
           any(C.term_matches(t, hay) for t in terms):
            best, label = m[tier], tier
            break

    fields_low = rec["fields"].lower().strip()
    genuinely_open = "ANY" in jel or fields_low.startswith("any field")
    bonus = m["open_field"] if genuinely_open else 0
    raw = best + bonus
    total = min(raw, m["cap"])
    bits = [b for b in (label, "open" if bonus else "") if b]
    if not bits:
        return 0, "match:none+0"
    capped = " capped" if raw > total else ""
    return total, f"match:{'+'.join(bits)}+{total}{capped}"


def score(rec: dict, cfg: dict, category: str) -> tuple[int, str]:
    parts = [geo_points(rec, cfg), field_points(rec, cfg),
             role_points(rec, cfg, category), match_points(rec, cfg)]
    return sum(p[0] for p in parts), " | ".join(p[1] for p in parts)


def triage(rec: dict, cfg: dict) -> dict:
    """Category, score, bucket.

    A/B/C are thresholds on the score, so they add no information the score does
    not carry; they are a convenience for grouping the review. `skip` is
    different and is NOT score-based: a Columbia adjunct scores 44 and a CEMFI
    pre-doc 40, and both would otherwise sit at the top of the list.

    If a weight in config.yml changes, re-check `bucket_cutoffs` against the new
    distribution or bucket A quietly becomes everything.
    """
    category = categorise(rec, cfg)
    rec["category"] = category
    rec["rank_hint"] = section_bucket(rec, category)
    rec["score"], rec["score_why"] = score(rec, cfg, category)
    if category in cfg["skip_categories"]:
        rec["bucket"] = "skip"
        rec["skip_reason"] = category.replace("_", " ")
    else:
        cut = cfg["bucket_cutoffs"]
        rec["bucket"] = ("A" if rec["score"] >= cut["A"]
                         else "B" if rec["score"] >= cut["B"] else "C")
        rec["skip_reason"] = ""
    return rec


GENERIC_INST_WORDS = {"university", "universite", "universitat", "college",
                      "institute", "school", "the", "of", "and", "for"}


INST_TYPE_WORDS = ["university", "college", "institute", "school", "bank", "laboratory"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def _inst_key(s: str) -> str:
    w = _norm(s).split()
    return " ".join(w[1:] if w and w[0] == "the" else w)


def _type_word(s: str) -> str:
    n = _norm(s)
    return next((t for t in INST_TYPE_WORDS if re.search(rf"\b{t}\b", n)), "")


def _distinctive(s: str) -> list[str]:
    return [w for w in _norm(s).split() if w not in GENERIC_INST_WORDS and len(w) > 2]


def _token_overlap(a: str, b: str) -> float:
    A, B = _distinctive(a), _distinctive(b)
    if not A or not B:
        return 0.0
    shared = 0
    for x in A:
        for y in B:
            if x == y or (len(x) >= 4 and y.startswith(x)) or (len(y) >= 4 and x.startswith(y)):
                shared += 1
                break
    return shared / min(len(A), len(B))


def same_institution(a: str, b: str, cfg: dict) -> bool:
    """Two institution names from different sites naming the same place.

    Deliberately conservative about the type word: dropping "University" and
    "College" as noise makes "Northwestern College" (Iowa) identical to
    "Northwestern University" (Illinois), which would merge two unrelated jobs.
    """
    d = cfg["duplicates"]
    if difflib.SequenceMatcher(None, _inst_key(a), _inst_key(b)).ratio() >= d["institution_similarity"]:
        return True
    ta, tb = _type_word(a), _type_word(b)
    return ta == tb != "" and _token_overlap(a, b) >= d["token_overlap"]


def _ad_text(cfg, uid: str) -> str:
    f = C.ads_dir(cfg) / f"{uid.replace(':', '_')}.txt"
    try:
        return " ".join(f.read_text(encoding="utf-8").split())[:2000]
    except OSError:
        return ""


def collapse_cross_posts(catalog: dict[str, dict], cfg: dict) -> tuple[int, int]:
    """Collapse ONE opening advertised on both JOE and EJM into a single row.

    Only ever across platforms. Two listings on the same site are never merged:
    the Atlanta Fed's three "Research Economist" ads are three separate searches
    (macro, labor, household finance) and the first is hiring two people.

    Collapsing requires everything essential to agree: same institution, same
    title, and the **same deadline**. That last one is the real gate. Ad body
    text is NOT thresholded, because the two sites format ads so differently
    that Brown's identical posting scores 0.07 similarity. Body text is used
    only to choose which partner pairs with which when one employer has several
    near-identical ads, where it is decisive: the Fed's correct pairs score 1.00
    against 0.53-0.72 for the wrong ones.

    Anything failing the test simply stays as two rows. That is harmless.
    """
    d = cfg["duplicates"]
    for r in catalog.values():
        r["duplicate"] = ""
        r["also_on"] = ""
    active = [r for r in catalog.values() if r.get("status") != C.EXPIRED]
    joe = [r for r in active if r["source"] == "JoE"]
    ejm = [r for r in active if r["source"].startswith("EJM")]

    index: dict[str, list[dict]] = {}
    for r in ejm:
        for tok in _distinctive(r["institution"]):
            index.setdefault(tok[:4], []).append(r)

    scored = []
    for j in joe:
        if not j.get("deadline"):
            continue
        seen: set[str] = set()
        for tok in _distinctive(j["institution"]):
            for e in index.get(tok[:4], []):
                if e["uid"] in seen:
                    continue
                seen.add(e["uid"])
                if e.get("deadline") != j["deadline"]:
                    continue
                if not same_institution(j["institution"], e["institution"], cfg):
                    continue
                ts = difflib.SequenceMatcher(None, _norm(j["title"]), _norm(e["title"])).ratio()
                if ts < d["title_similarity"]:
                    continue
                body = difflib.SequenceMatcher(
                    None, _ad_text(cfg, j["uid"]), _ad_text(cfg, e["uid"])).ratio()
                scored.append((body, ts, j, e))

    scored.sort(key=lambda x: (-x[0], -x[1]))
    taken_j, taken_e, n = set(), set(), 0
    for body, ts, j, e in scored:
        if j["uid"] in taken_j or e["uid"] in taken_e:
            continue
        taken_j.add(j["uid"])
        taken_e.add(e["uid"])
        n += 1
        # EJM survives: it usually also handles the application and the letters.
        j["duplicate"] = e["uid"]
        e["also_on"] = j["uid"]
    return n, len(active) - 2 * n
