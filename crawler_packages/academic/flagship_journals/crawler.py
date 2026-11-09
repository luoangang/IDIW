from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


JOURNALS = {
    "nature": ("Nature", "0028-0836"),
    "science": ("Science", "0036-8075"),
    "pnas": ("Proceedings of the National Academy of Sciences", "0027-8424"),
    "cell": ("Cell", "0092-8674"),
}
API = "https://api.openalex.org/works"
MAX_BYTES = 5_000_000
MAX_ARTICLE_BYTES = 2_000_000
USER_AGENT = "IntelligenceCollector-FlagshipJournals/1.0 (public metadata)"
EXCLUDED_TITLE = re.compile(r"^(?:correction|erratum|retraction|expression of concern|publisher correction)\b", re.I)
BEIJING = timezone(timedelta(hours=8))


def clean(value):
    if not isinstance(value, str):
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


class NatureAbstractParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.sup_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if self.depth == 0:
            if tag == "div" and dict(attrs).get("id") == "Abs1-content":
                self.depth = 1
        elif tag not in {"br", "hr", "img", "wbr"}:
            self.depth += 1
            if tag == "sup":
                self.sup_depth += 1

    def handle_endtag(self, tag):
        if self.depth and tag not in {"br", "hr", "img", "wbr"}:
            if tag == "sup" and self.sup_depth:
                self.sup_depth -= 1
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and not self.sup_depth:
            self.parts.append(data)

    def abstract(self):
        return " ".join(" ".join(self.parts).split()) or None


def nature_abstract(doi, timeout):
    if not doi.startswith("10.1038/s41586-"):
        return None
    article_id = doi.split("/", 1)[1]
    url = "https://www.nature.com/articles/" + article_id
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_ARTICLE_BYTES + 1)
        if len(raw) > MAX_ARTICLE_BYTES:
            return None
        parser = NatureAbstractParser()
        parser.feed(raw.decode("utf-8", errors="replace"))
        return parser.abstract()
    except (OSError, ValueError):
        return None


def abstract_from_index(index):
    if not isinstance(index, dict):
        return None
    positions = {}
    for word, offsets in index.items():
        if not isinstance(word, str) or not isinstance(offsets, list):
            continue
        for offset in offsets:
            if isinstance(offset, int) and 0 <= offset < 100_000:
                positions[offset] = word
    if not positions:
        return None
    return " ".join(positions[position] for position in sorted(positions))


def doi_value(value):
    if not isinstance(value, str):
        return ""
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.I)
    return doi.lower() if re.fullmatch(r"10\.\d{4,9}/\S+", doi, re.I) else ""


def get_json(url, timeout):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("API response exceeds 5 MB")
            return json.loads(raw)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                break
            retry_after = exc.headers.get("Retry-After", "")
            delay = min(5, int(retry_after)) if retry_after.isdigit() else 1 + attempt * 2
            time.sleep(delay)
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(1 + attempt * 2)
    raise RuntimeError(f"API request failed: {last_error}")


def date_window(request, lookback_days):
    window = request.get("time_range") or {}
    today = datetime.now(BEIJING).date()
    start = window.get("from") or ((today - timedelta(days=lookback_days)).isoformat() if lookback_days else None)
    end = window.get("to") or today.isoformat()
    for value in (start, end):
        if value is not None:
            date.fromisoformat(value)
    if start and start > end:
        raise ValueError("time_range.from must be no later than time_range.to")
    return start, end


def query_terms(request):
    params = request.get("parameters") or {}
    values = [request.get("query", ""), *(request.get("aliases") or []), *(params.get("search_terms") or [])]
    terms = []
    for value in values:
        term = clean(value)
        if term and term.casefold() not in {known.casefold() for known in terms}:
            terms.append(term)
    if not terms or len(terms) > 10:
        raise ValueError("provide 1 to 10 distinct query terms including aliases/search_terms")
    if not any(re.search(r"[A-Za-z]", term) for term in terms):
        raise ValueError("English search term required in aliases or search_terms for these journals")
    return terms


def search_url(issn, terms, start, end, page, api_key):
    filters = [f"primary_location.source.issn:{issn}", "type:article", f"to_publication_date:{end}"]
    if start:
        filters.append(f"from_publication_date:{start}")
    query = {
        "filter": ",".join(filters),
        "search.title_and_abstract": " OR ".join('"' + term.replace('"', "") + '"' for term in terms),
        "per_page": 100,
        "page": page,
        "sort": "publication_date:desc",
        "select": "id,doi,title,publication_date,publication_year,primary_location,authorships,abstract_inverted_index,biblio,language,open_access,cited_by_count,type",
    }
    if api_key:
        query["api_key"] = api_key
    return API + "?" + urlencode(query)


def matched_terms(title, abstract, terms):
    text = f"{title} {abstract or ''}".casefold()
    return [term for term in terms if term.casefold() in text]


def normalize(work, key, terms):
    if not isinstance(work, dict):
        return None
    doi = doi_value(work.get("doi"))
    title = clean(work.get("title"))
    if not doi or not title or EXCLUDED_TITLE.search(title):
        return None
    if key == "nature" and doi.startswith("10.1038/d41586-"):
        return None
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    source_issns = {source.get("issn_l"), *(source.get("issn") or [])}
    if JOURNALS[key][1] not in source_issns:
        return None
    abstract = abstract_from_index(work.get("abstract_inverted_index"))
    authors, affiliations = [], []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        name = clean(author.get("display_name"))
        if name and name not in authors:
            authors.append(name)
        for institution in authorship.get("institutions") or []:
            institution_name = clean(institution.get("display_name"))
            if institution_name and institution_name not in affiliations:
                affiliations.append(institution_name)
    biblio = work.get("biblio") or {}
    publication_date = work.get("publication_date")
    if publication_date:
        try:
            publication_date = date.fromisoformat(publication_date).isoformat()
        except (TypeError, ValueError):
            publication_date = None
    open_access = work.get("open_access") or {}
    return {
        "doi": doi, "journal_key": key, "journal_name": JOURNALS[key][0],
        "issn": JOURNALS[key][1], "title": title[:1000],
        "url": location.get("landing_page_url") or f"https://doi.org/{doi}",
        "authors": authors, "affiliations": affiliations,
        "abstract": abstract, "abstract_source": "openalex" if abstract else None,
        "published_at": publication_date, "year": work.get("publication_year"),
        "volume": str(biblio["volume"])[:64] if biblio.get("volume") else None,
        "issue": str(biblio["issue"])[:64] if biblio.get("issue") else None,
        "pages": str(biblio["first_page"])[:128] + ("-" + str(biblio["last_page"]) if biblio.get("last_page") else "") if biblio.get("first_page") else None,
        "language": work.get("language"), "open_access": open_access.get("is_oa"),
        "cited_by_count": work.get("cited_by_count"), "openalex_id": work.get("id") or "",
        "matched_terms": matched_terms(title, abstract, terms),
    }


def enrich_crossref(item, timeout):
    if item["abstract"]:
        return
    try:
        response = get_json("https://api.crossref.org/works/" + quote(item["doi"], safe=""), timeout)
        abstract = clean((response.get("message") or {}).get("abstract"))
    except (RuntimeError, ValueError, TypeError, KeyError):
        return
    if abstract:
        item["abstract"] = abstract
        item["abstract_source"] = "crossref"


def enrich_nature(item, timeout):
    if item["journal_key"] != "nature" or item["abstract"]:
        return
    abstract = nature_abstract(item["doi"], timeout)
    if abstract:
        item["abstract"] = abstract
        item["abstract_source"] = "nature"


def collect(request, fetch=get_json):
    params = request.get("parameters") or {}
    keys = params.get("journal_keys", list(JOURNALS))
    terms = query_terms(request)
    start, end = date_window(request, params.get("lookback_days", 30))
    per_journal = params.get("per_journal_limit", 100)
    timeout = params.get("timeout_seconds", 20)
    limit = request["limit"]
    api_key = os.getenv("CRAWLER_SECRET_OPENALEX_API_KEY", "")
    items, warnings, succeeded = {}, [], 0
    for key in keys:
        if key not in JOURNALS:
            raise ValueError(f"unsupported journal: {key}")
        checked = 0
        try:
            for page in range(1, (per_journal + 99) // 100 + 1):
                response = fetch(search_url(JOURNALS[key][1], terms, start, end, page, api_key), timeout)
                rows = response.get("results") if isinstance(response, dict) else None
                if not isinstance(rows, list) or not isinstance(response.get("meta"), dict):
                    raise ValueError("invalid OpenAlex search response")
                remaining = per_journal - checked
                for work in rows[:remaining]:
                    item = normalize(work, key, terms)
                    if item and item["doi"] not in items:
                        items[item["doi"]] = item
                checked += min(len(rows), remaining)
                if len(rows) < 100 or checked >= per_journal:
                    break
            total = response["meta"].get("count", 0)
            if isinstance(total, int) and total > per_journal:
                warnings.append(f"{key}: {total} candidates, inspected first {per_journal}")
            succeeded += 1
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            warnings.append(f"{key}: {exc}")
    if not succeeded:
        raise RuntimeError("all journal searches failed: " + "; ".join(warnings))
    ordered = sorted(items.values(), key=lambda row: (row["published_at"] or "", row["doi"]), reverse=True)
    if len(ordered) > limit:
        warnings.append(f"global limit {limit} truncated {len(ordered) - limit} records")
    ordered = ordered[:limit]
    missing = [item for item in ordered if not item["abstract"]]
    for item in missing[:20]:
        enrich_nature(item, timeout)
        if not item["abstract"]:
            enrich_crossref(item, timeout)
    if len(missing) > 20:
        warnings.append(f"abstract lookups capped at 20 of {len(missing)} missing abstracts")
    if params.get("require_abstract", False):
        ordered = [item for item in ordered if item["abstract"]]
    return ordered, warnings, succeeded < len(keys)


def write_output(output_dir, request, items, warnings, partial, error=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    result = {
        "protocol_version": "1.0", "execution_id": request["execution_id"],
        "status": "failed" if error else "partial" if partial else "completed",
        "item_count": len(items), "next_cursor": None, "has_more": False,
        "warnings": warnings, "error": error,
    }
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8-sig"))
    try:
        items, warnings, partial = collect(request)
        write_output(args.output, request, items, warnings, partial)
        return 0
    except (RuntimeError, ValueError, TypeError, KeyError) as exc:
        write_output(args.output, request, [], [], False, {"code": "COLLECTION_FAILED", "message": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
