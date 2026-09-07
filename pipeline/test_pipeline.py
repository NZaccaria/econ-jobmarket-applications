"""Regression tests for the triage rules.

Every case here is a bug that actually shipped during development, or the
precise boundary that separates it from a correct classification. The rules are
pattern matching over free text, so the failure mode is silent misclassification
rather than a crash: a job quietly demoted is a job you never see.

Run:  python3 -m pytest 00_pipeline/test_pipeline.py -q
      python3 00_pipeline/test_pipeline.py        (same, without pytest)

No network and no Google credentials: everything here is a pure function.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import sources  # noqa: E402
import triage as T  # noqa: E402

CFG = C.load_config()


def rec(title="", section="", source="JoE", department="", fields="",
        jel="", country="", city=""):
    return {"title": title, "section": section, "source": source,
            "department": department, "fields": fields, "jel": jel,
            "country": country, "city": city}


# --------------------------------------------------------------------------
# categorise: what KIND of post this is. Never about field.
# --------------------------------------------------------------------------

def test_international_is_not_an_internship():
    """`intern` as a substring matched inside "International" and demoted 40
    tenure-track jobs, Bocconi and Texas A&M macro among them."""
    assert T.categorise(rec("Assistant Professor of International and Public Affairs"), CFG) == "faculty"
    assert T.categorise(rec("Assistant Professor of International Macroeconomics"), CFG) == "faculty"
    assert T.categorise(rec("Summer Internship Programme"), CFG) == "internship"


def test_phd_in_a_title_usually_means_a_phd_is_required():
    """"PhD Economist" at the NY Fed is a job for someone who HAS a PhD."""
    assert T.categorise(rec("PhD Economist"), CFG) == "economist"
    assert T.categorise(rec("Associate, PhD - Early Decision (Economics Focus)"), CFG) != "phd_student"
    assert T.categorise(rec("PhD position in Economics: renewable energy auctions"), CFG) == "phd_student"
    assert T.categorise(rec("Doctoral Researchers/PhD - Gender"), CFG) == "phd_student"


def test_postdoc_beats_doctoral():
    """"Post-Doctoral Researcher" must not be read as a doctoral student."""
    assert T.categorise(rec("Post-Doctoral Researcher"), CFG) == "postdoc"
    assert T.categorise(rec("Postdoctoral Fellow"), CFG) == "postdoc"


def test_research_assistant_professor_is_faculty():
    """A rank, not a research assistant post."""
    assert T.categorise(rec("Research Assistant Professor of Health Policy"), CFG) == "faculty"
    assert T.categorise(rec("Research Assistant (Pre-Doc)", source="EJM",
                            section="Research Assistant (Pre-Doc)"), CFG) == "predoc"


def test_open_rank_naming_assistant_first_is_not_senior_only():
    """A forward-only lookahead missed "Assistant" when it came first, skipping
    open-rank searches at Brown, Stanford and Yale."""
    assert T.categorise(rec("Assistant, Associate, or Full Professor Rank"), CFG) == "faculty"
    assert T.categorise(rec("Tenure-Track Assistant/Associate/Full Professor"), CFG) == "faculty"
    assert T.categorise(rec("Full Professorship"), CFG) == "senior_only"
    assert T.categorise(rec("Associate/Full Professor, Financial Economics"), CFG) == "senior_only"


def test_adjunct_from_joe_section_only():
    assert T.categorise(rec("Adjunct Faculty- Economics"), CFG) == "adjunct"
    assert T.categorise(rec("Economist", section="US: Other Academic (Part-time or Adjunct)"),
                        CFG) == "adjunct"


# --------------------------------------------------------------------------
# role: JOE's section is a shelf label, not a rank list.
# --------------------------------------------------------------------------

def test_joe_full_time_academic_is_not_a_full_professorship():
    """`\\bfull\\b` matched inside "Full-Time Academic", so every JOE academic
    ad looked bundled with a senior hire: 70 assistant professorships were
    scored open-rank and 45 fell through to role:other."""
    r = rec("Tenure-Track Professor in Economics",
            section="US: Full-Time Academic (Permanent, Tenure Track or Tenured)")
    pts, why = T.role_points(r, CFG, "faculty")
    assert pts == CFG["scoring"]["role"]["assistant"], why


def test_ejm_section_is_a_real_rank_list():
    r = rec("Assistant, Advanced Assistant, Associate, or Full Professor of Economics",
            section="Assistant Professor • Associate Professor • Full Professor",
            source="EJM")
    pts, why = T.role_points(r, CFG, "faculty")
    assert pts == CFG["scoring"]["role"]["open_rank"], why


# --------------------------------------------------------------------------
# geography
# --------------------------------------------------------------------------

def test_joe_location_keeps_only_the_leading_country_run():
    """"UNITED STATES Indiana NOTRE DAME" produced the country "United States
    Notre Dame", matching no list, so 17 US jobs scored zero for geography."""
    city, country = sources.split_joe_location("UNITED STATES Indiana NOTRE DAME")
    assert country == "United States"
    pts, why = T.geo_points({"country": country, "city": city}, CFG)
    assert pts == CFG["scoring"]["geography"]["priority"], why


def test_geo_tiers():
    prio = CFG["scoring"]["geography"]["priority"]
    sec = CFG["scoring"]["geography"]["secondary"]
    assert T.geo_points({"country": "Germany", "city": "Bonn"}, CFG)[0] == prio
    assert T.geo_points({"country": "Canada", "city": "Vancouver"}, CFG)[0] == sec
    assert T.geo_points({"country": "China", "city": "Guangzhou"}, CFG)[0] == 0


# --------------------------------------------------------------------------
# field: the department is honest, the advertised field list is marketing.
# --------------------------------------------------------------------------

def test_fintech_department_is_not_economics_however_it_advertises():
    r = rec("Open-rank faculty position in Fintech/Financial Engineering",
            department="Financial Technology",
            fields="Finance • Macroeconomics; Monetary • Behavioral")
    assert T.field_points(r, CFG)[0] == 0


def test_department_naming_no_discipline_falls_back_to_fields():
    """"MIT FutureTech" names no discipline; its field list is the only signal."""
    r = rec("Post-Doctoral Associate", department="MIT FutureTech",
            fields="Economics of AI Industrial Organization")
    assert T.field_points(r, CFG)[0] == CFG["scoring"]["field"]["economics"]


# --------------------------------------------------------------------------
# matching keywords
# --------------------------------------------------------------------------

def test_short_terms_match_whole_words_only():
    """A substring test makes "AI" match "chair" and "training"."""
    assert C.term_matches("AI", "Economics of AI")
    assert not C.term_matches("AI", "Chair Professor of Economics")
    assert not C.term_matches("AI", "Training and Development")


def test_profile_tiers_load():
    """Structure, not content: this must pass for ANY candidate's profile.md,
    so it cannot assert on one person's fields."""
    p = C.load_profile()
    for tier in ("tier1", "tier2", "tier3"):
        assert isinstance(p[tier]["terms"], list), f"{tier} terms must be a list"
        assert isinstance(p[tier]["jel"], list), f"{tier} jel must be a list"
    assert p["tier1"]["terms"] or p["tier1"]["jel"], \
        "tier1 is empty: nothing would ever score as a strong match"
    for tier in ("tier1", "tier2", "tier3"):
        for code in p[tier]["jel"]:
            assert re.fullmatch(r"[A-Z]\d", code), f"bad JEL code {code!r} in {tier}"


# --------------------------------------------------------------------------
# institution matching for cross-posted openings
# --------------------------------------------------------------------------

def test_institution_matching():
    same = [("The University of Hong Kong", "University of Hong Kong"),
            ("Tennessee Technological University", "Tennessee Tech University"),
            ("OECD- Organisation for Economic Cooperation",
             "OECD (Organisation for Economic Co-operation")]
    for a, b in same:
        assert T.same_institution(a, b, CFG), f"{a} vs {b} should match"

    # "University" and "College" are NOT noise: dropping them merges
    # Northwestern College (Iowa) into Northwestern University (Illinois).
    different = [("Northwestern College", "Northwestern University"),
                 ("Musashi University", "Monash University"),
                 ("University of Tsukuba", "University of Utah"),
                 ("Nanjing University", "Jinan University")]
    for a, b in different:
        assert not T.same_institution(a, b, CFG), f"{a} vs {b} must NOT match"


# --------------------------------------------------------------------------
# invariants
# --------------------------------------------------------------------------

def test_why_always_sums_to_the_score():
    """The Why column is the only explanation of a score, so it must add up.
    The match cap was once applied to the number but not to the label."""
    samples = [
        rec("Assistant Professor of Economics", department="Economics",
            country="United States", jel="E3 E4", fields="Macroeconomics"),
        rec("Assistant Professor", department="Economics", country="Ireland",
            jel="", fields="Any field"),
        rec("Economist", department="Research", country="China", jel="J2"),
        rec("Postdoctoral Fellow", department="Economics", country="Canada",
            fields="Any field", jel="E3"),
    ]
    for r in samples:
        out = T.triage(dict(r), CFG)
        parts = sum(int(x) for x in re.findall(r"\+(\d+)", out["score_why"]))
        assert parts == out["score"], f"{out['score_why']} != {out['score']}"


def test_skip_is_not_score_based():
    """A Columbia adjunct scores 44 and a CEMFI pre-doc 40; both must still be
    demoted, which is why `skip` cannot be a threshold on the score."""
    out = T.triage(rec("Assistant/Associate/Full Adjunct Professor - Economics",
                       department="Economics", country="United States"), CFG)
    assert out["bucket"] == "skip" and out["score"] > CFG["bucket_cutoffs"]["B"]


def test_a1_notation():
    import sheet as S
    assert S.a1(0, 1) == "A1"
    assert S.a1(22, 2) == "W2"      # the uid column on Applications
    assert S.a1(25, 1) == "Z1"
    assert S.a1(26, 3) == "AA3"


def test_rows_are_built_by_header_name():
    """Adding a column must not shift existing data into the wrong column."""
    import sheet as S
    row = S.row_from(S.APP_HEADERS, {"Institution": "X", "uid": "u1"})
    assert len(row) == len(S.APP_HEADERS)
    assert row[S.col(S.APP_HEADERS, "Institution")] == "X"
    assert row[S.col(S.APP_HEADERS, "uid")] == "u1"

    extended = S.APP_HEADERS[:5] + ["Brand New"] + S.APP_HEADERS[5:]
    moved = S.row_from(extended, {"Institution": "X", "uid": "u1"})
    assert moved[S.col(extended, "Institution")] == "X"
    assert moved[S.col(extended, "uid")] == "u1"
    assert moved[S.col(extended, "Brand New")] == ""


def test_tickbox_columns_are_real_headers():
    import sheet as S
    for name in S.APP_TICKBOXES:
        assert name in S.APP_HEADERS, name


def test_no_local_name_shadows_the_col_helper():
    """`for col, width in ...` inside format_applications shadowed the module
    level col() helper, so formatting the Applications tab raised
    UnboundLocalError. Nothing caught it because it needs a live spreadsheet."""
    src = (Path(__file__).resolve().parent / "sheet.py").read_text(encoding="utf-8")
    offenders = [ln.strip() for ln in src.splitlines()
                 if re.match(r"\s*for\s+col\b", ln) or re.match(r"\s*col\s*=", ln)]
    assert not offenders, f"these rebind the col() helper: {offenders}"


def test_column_widths_reference_real_headers():
    """Width tables are keyed by header name; a typo would raise at runtime
    inside a Sheets call, which no unit test reaches."""
    import sheet as S
    src = (Path(__file__).resolve().parent / "sheet.py").read_text(encoding="utf-8")
    for block, headers in (("widths = {", S.INBOX_HEADERS),
                           ("app_widths = {", S.APP_HEADERS)):
        chunk = src[src.index(block):]
        chunk = chunk[:chunk.index("}")]
        for name in re.findall(r'"([^"]+)":', chunk):
            assert name in headers, f"{name!r} is not a header"


def test_apps_script_headers_exist_in_python():
    """The spreadsheet button resolves columns by header NAME, so the names it
    needs must exist in sheet.py. Renaming a header there would otherwise break
    the button silently, at the moment it writes rows into Applications."""
    import sheet as S
    gs = (Path(__file__).resolve().parent / "AppsScript.gs").read_text(encoding="utf-8")

    def names(var):
        m = re.search(var + r"\s*=\s*\[(.*?)\];", gs, re.S)
        assert m, f"{var} not found in AppsScript.gs"
        return [x.strip().strip("'") for x in m.group(1).replace("\n", " ").split(",")
                if x.strip()]

    for var, headers in (("INBOX_NEEDS", S.INBOX_HEADERS),
                         ("APPS_NEEDS", S.APP_HEADERS),
                         ("APPS_TICKBOXES", S.APP_HEADERS)):
        missing = [n for n in names(var) if n not in headers]
        assert not missing, f"{var} refers to headers sheet.py does not define: {missing}"


def test_apps_script_never_writes_notes():
    """Notes belongs to the user. Both writers must leave it empty."""
    gs = (Path(__file__).resolve().parent / "AppsScript.gs").read_text(encoding="utf-8")
    assert "'Notes': ''" in gs


if __name__ == "__main__":
    import traceback
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception:
            bad += 1
            print(f"  FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(fns) - bad}/{len(fns)} passed")
    raise SystemExit(1 if bad else 0)
