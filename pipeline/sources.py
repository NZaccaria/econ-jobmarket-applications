"""Where listings come from: JOE and EJM.

Fetching and parsing only. Nothing here scores or judges a listing.

JOE publishes its own XLSX export, so that half needs no scraping. EJM does
not, so its cards are parsed out of the rendered HTML, which makes it the
fragile side: see the count assertion in fetch_ejm.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


JOE_LIST = "https://www.aeaweb.org/joe/listings"


EJM_LIST = "https://econjobmarket.org/positions"


EJM_RA_LIST = "https://econjobmarket.org/market"


EJM_MAX_PAGES = 40


TIMEOUT = 60


def get(url: str) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r


def fetch_joe() -> list[dict]:
    import pandas as pd

    page = get(JOE_LIST).text
    m = re.search(r'href="(/joe/resultset_xls_output\.php[^"]*)"', page)
    if not m:
        raise RuntimeError(
            "JOE export link not found on the listings page. The site layout "
            "probably changed; check https://www.aeaweb.org/joe/listings by hand."
        )
    export_url = "https://www.aeaweb.org" + m.group(1).replace("&amp;", "&")
    blob = get(export_url).content
    df = pd.read_excel(io.BytesIO(blob))

    out = []
    for _, r in df.iterrows():
        joe_id = f"{C.clean(r.get('joe_issue_ID'))}_{C.clean(r.get('jp_id'))}"
        city, country = split_joe_location(r.get("locations"))
        jel = extract_jel(r.get("JEL_Classifications"))
        out.append({
            "uid": f"joe:{joe_id}",
            "source": "JoE",
            "institution": C.clean(r.get("jp_institution")),
            "department": C.clean(r.get("jp_department")) or C.clean(r.get("jp_division")),
            "title": C.clean(r.get("jp_title")),
            "section": C.clean(r.get("jp_section")),
            "fields": C.clean(r.get("jp_keywords"))[:300],
            "jel": " ".join(jel),
            "city": city,
            "country": country,
            "deadline": C.parse_date(r.get("Application_deadline")),
            "posted": C.parse_date(r.get("Date_Active")),
            "letters_required": "",
            "url": f"https://www.aeaweb.org/joe/listing.php?JOE_ID={joe_id}",
            "_full_text": str(r.get("jp_full_text") or ""),
        })
    return out


def split_joe_location(value) -> tuple[str, str]:
    """'UNITED STATES Minnesota Minneapolis' -> ('Minneapolis', 'UNITED STATES')."""
    s = C.clean(value)
    if not s:
        return "", ""
    # Only the LEADING run of uppercase tokens is the country. JOE writes
    # "UNITED STATES Indiana NOTRE DAME", and taking every uppercase token made
    # the country "United States Notre Dame", which matched no country list and
    # scored 0 for geography on a job in Indiana.
    parts = s.split()
    caps = []
    for p in parts:
        if p.isupper() and len(p) > 1:
            caps.append(p)
        else:
            break
    country = " ".join(caps)
    rest = s[len(country):].strip() if country else s
    return rest, country.title()


def extract_jel(value) -> list[str]:
    """Two-character JEL prefixes. '00' is JOE's marker for an open-field ad."""
    s = str(value or "")
    if "Any Field" in s or re.match(r"^\s*00\b", s):
        return ["ANY"]
    return sorted(set(re.findall(r"\b([A-Z]\d)\b", s)))


def fetch_ejm(base_url: str = EJM_LIST, source: str = "EJM") -> list[dict]:
    """Every page of EJM's regular postings.

    EJM paginates at 50 and states its own total ("92 positions found"). The
    parsed count is checked against that total and a mismatch raises, because a
    silently truncated listing is the failure that actually costs a job.
    """
    out: list[dict] = []
    seen: set[str] = set()
    reported = None

    for page in range(1, EJM_MAX_PAGES + 1):
        url = base_url if page == 1 else f"{base_url}?page={page}"
        html = get(url).text
        html = re.sub(r"<!--\[if (?:BLOCK|ENDBLOCK)\]><!\[endif\]-->", "", html)
        if reported is None:
            m = re.search(r"([\d,]+)\s+positions?\s+found", html)
            reported = int(m.group(1).replace(",", "")) if m else None
        rows = _parse_ejm_page(html, source)
        fresh = [r for r in rows if r["uid"] not in seen]
        if not fresh:
            break
        seen.update(r["uid"] for r in fresh)
        out.extend(fresh)

    if reported is not None and len(out) != reported:
        raise RuntimeError(
            f"EJM said {reported} positions but {len(out)} were parsed. "
            "Pagination or the card markup changed; fix the parser before trusting this."
        )
    return out


def _parse_ejm_page(html: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", id=re.compile(r"^title-\d+$")):
        pid = a["id"].split("-", 1)[1]
        card = a.find_parent("div", class_="card")
        if card is None:
            continue
        cols4 = card.find_all("div", class_="col-md-4")
        cols2 = card.find_all("div", class_="col-md-2")

        title = C.clean(a.get_text())
        city, country = ejm_location(cols4[0], title) if cols4 else ("", "")

        # col-md-4[1] is department lines then the institution on the last line.
        institution, department = "", ""
        if len(cols4) > 1:
            lines = [C.clean(x) for x in cols4[1].get_text("\n", strip=True).split("\n") if C.clean(x)]
            if lines:
                institution = lines[-1]
                department = " / ".join(lines[:-1])

        # col-md-2[0] holds position types, then <hr class="type-field-separator">,
        # then the research fields. Splitting on that hr is what keeps ranks like
        # "Associate Professor" out of the fields column.
        cats, fields = "", ""
        if cols2:
            cats, fields = ejm_types_and_fields(cols2[0])

        # col-md-2[1] holds dates: .bg-info is the posting date, .negative the
        # deadline. Most ads state the deadline only here, not in the body.
        posted, deadline = "", ""
        if len(cols2) > 1:
            tag = cols2[1].find(class_="bg-info")
            posted = C.parse_date(tag.get_text()) if tag else ""
            tag = cols2[1].find(class_="negative")
            deadline = C.parse_date(tag.get_text()) if tag else ""

        body = card.find("div", class_="collapse")
        full_text = body.get_text("\n", strip=True) if body else ""
        if not deadline:
            deadline = C.parse_date(labelled(full_text, "Application deadline"))

        out.append({
            "uid": f"ejm:{pid}",
            "source": source,
            "institution": institution,
            "department": department,
            "title": title,
            "section": cats,
            "fields": fields[:300],
            "jel": "",
            "city": city,
            "country": country,
            "deadline": deadline,
            "posted": posted,
            "letters_required": labelled(full_text, "Letters of reference required"),
            "url": f"https://econjobmarket.org/positions/{pid}",
            "_full_text": full_text,
        })
    return out


def ejm_types_and_fields(col) -> tuple[str, str]:
    hr = col.find("hr", class_="type-field-separator")
    if hr is None:
        text = C.clean(col.get_text(" ", strip=True))
        return text, ""
    before, after = [], []
    target = before
    for node in col.children:
        if node is hr:
            target = after
            continue
        target.append(node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node))
    types = C.clean(" ".join(before)).replace("\u2022", "•")
    fields = C.clean(" ".join(after))
    return types, fields


def ejm_location(col, title: str) -> tuple[str, str]:
    """'Williamstown, United States (map).' -> ('Williamstown', 'United States')."""
    text = C.clean(col.get_text(" ", strip=True))
    if title and text.startswith(title):
        text = text[len(title):]
    # get_text(" ") turns the map link into "( map )", so match it tolerantly.
    text = re.sub(r"\(\s*map\s*\)", "", text)
    text = re.split(r"\(\s*map|Starts|Duration|Flexible start", text)[0]
    text = C.clean(text).strip(" .(")
    if not text:
        return "", ""
    if "," in text:
        city, _, country = text.rpartition(",")
        return C.clean(city), C.clean(country)
    return text, ""


def labelled(text: str, label: str) -> str:
    m = re.search(rf"{re.escape(label)}\s*:\s*(.+)", text)
    return C.clean(m.group(1))[:60] if m else ""
