from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


JOURNALS = {
    row["journal_key"]: row
    for row in json.loads((Path(__file__).with_name("journals.json")).read_text(encoding="utf-8"))
}
DEFAULT_KEYS = ["91951a14a7ce0ca5", "e60fb00be47651cc", "423b8321d3ff24ce"]
OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
USER_AGENT = "IDIW-OpenAlexCrossrefJournals/1.0 (public metadata)"
MAX_BYTES = 8_000_000
EXCLUDED_TITLE = re.compile(
    r"^(?:editorial|correction|corrigendum|erratum|retraction|expression of concern|"
    r"publisher correction|guest editorial|in this issue|contents)\b",
    re.I,
)


class SourceUnavailable(Exception):
    pass


def clean(value):
    if value is None:
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", str(value))).split())


def date_text(parts):
    if not isinstance(parts, list) or not parts:
        return None
    if isinstance(parts[0], list):
        parts = parts[0]
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return date(year, month, day).isoformat()
    except (TypeError, ValueError):
        return None


def abstract_from_index(index):
    if not isinstance(index, dict) or not index:
        return None
    positions = [pos for values in index.values() for pos in values if isinstance(pos, int)]
    if not positions:
        return None
    words = [""] * (max(positions) + 1)
    for word, values in index.items():
        for pos in values:
            if isinstance(pos, int) and 0 <= pos < len(words):
                words[pos] = word
    return clean(" ".join(word for word in words if word)) or None


def request_json(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise SourceUnavailable("response exceeds 8 MB")
            return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {429, 500, 502, 503, 504}:
            raise SourceUnavailable(f"HTTP {exc.code}") from exc
        raise
    except (URLError, TimeoutError, ValueError) as exc:
        raise SourceUnavailable(f"{type(exc).__name__}: {exc}") from exc


def requested_terms(request_data, parameters):
    values = list(parameters.get("search_terms") or [])
    values += list(request_data.get("aliases") or [])
    values.append(request_data.get("query", ""))
    terms = []
    for value in values:
        text = clean(value)
        if text and text not in terms:
            terms.append(text)
    return terms[:5]


def date_window(request_data, lookback_days):
    time_range = request_data.get("time_range") or {}
    today = datetime.now(timezone.utc).date()
    start = clean(time_range.get("from")) or (today - timedelta(days=lookback_days)).isoformat()
    end = clean(time_range.get("to")) or today.isoformat()
    return start[:10], end[:10]


def deadline_reached(value):
    try:
        return datetime.now(timezone.utc) >= datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False


def openalex_url(issn, term, mode, start, end, cursor):
    filters = [
        f"primary_location.source.issn:{issn}",
        f"from_publication_date:{start}",
        f"to_publication_date:{end}",
    ]
    parameters = {
        "filter": ",".join(filters),
        "per-page": "100",
        "cursor": cursor,
        "sort": "publication_date:desc",
    }
    if mode == "keywords" and term:
        parameters["search"] = term
    api_key = os.getenv("CRAWLER_SECRET_OPENALEX_API_KEY", "").strip()
    if api_key:
        parameters["api_key"] = api_key
    return OPENALEX + "?" + urlencode(parameters)


def crossref_url(issn, term, mode, start, end, rows, offset):
    filters = [f"issn:{issn}", f"from-pub-date:{start}", f"until-pub-date:{end}"]
    parameters = {
        "filter": ",".join(filters),
        "rows": str(rows),
        "offset": str(offset),
        "sort": "published",
        "order": "desc",
    }
    if mode == "keywords" and term:
        parameters["query.bibliographic"] = term
    return CROSSREF + "?" + urlencode(parameters)


def openalex_record(work, journal, issn, terms):
    doi = clean(work.get("doi")).replace("https://doi.org/", "").replace("http://doi.org/", "").lower()
    title = clean(work.get("display_name"))[:1000]
    if not doi or not title or EXCLUDED_TITLE.match(title):
        return None
    authors, affiliations = [], []
    for authorship in work.get("authorships") or []:
        name = clean((authorship.get("author") or {}).get("display_name"))
        if name and name not in authors:
            authors.append(name)
        for institution in authorship.get("institutions") or []:
            affiliation = clean(institution.get("display_name"))
            if affiliation and affiliation not in affiliations:
                affiliations.append(affiliation)
    abstract = abstract_from_index(work.get("abstract_inverted_index"))
    biblio = work.get("biblio") or {}
    first, last = clean(biblio.get("first_page")), clean(biblio.get("last_page"))
    pages = f"{first}-{last}" if first and last and first != last else (first or last or None)
    published_at = clean(work.get("publication_date")) or None
    text = f"{title} {abstract or ''}".casefold()
    return {
        "doi": doi[:255], "journal_key": journal["journal_key"],
        "journal_name": journal["name"][:255], "issn": issn,
        "title": title, "url": f"https://doi.org/{doi}",
        "authors": authors, "affiliations": affiliations,
        "abstract": abstract, "published_at": published_at,
        "year": int(work.get("publication_year")) if work.get("publication_year") else None,
        "volume": clean(biblio.get("volume"))[:64] or None,
        "issue": clean(biblio.get("issue"))[:64] or None,
        "pages": pages[:128] if pages else None,
        "language": clean(work.get("language"))[:16] or None,
        "open_access": bool((work.get("open_access") or {}).get("is_oa")) if work.get("open_access") else None,
        "cited_by_count": int(work["cited_by_count"]) if work.get("cited_by_count") is not None else None,
        "source_api": "openalex", "openalex_id": clean(work.get("id"))[:128] or None,
        "matched_terms": [term for term in terms if term.casefold() in text],
    }


def crossref_record(item, journal, issn, terms):
    doi = clean(item.get("DOI")).lower()
    title = clean((item.get("title") or [""])[0])[:1000]
    if not doi or not title or item.get("type") != "journal-article" or EXCLUDED_TITLE.match(title):
        return None
    authors, affiliations = [], []
    for author in item.get("author") or []:
        name = clean(" ".join(value for value in (author.get("given"), author.get("family")) if value))
        if name and name not in authors:
            authors.append(name)
        for affiliation in author.get("affiliation") or []:
            value = clean(affiliation.get("name"))
            if value and value not in affiliations:
                affiliations.append(value)
    published = item.get("published") or item.get("published-print") or item.get("published-online") or item.get("issued") or {}
    published_at = date_text(published.get("date-parts"))
    abstract = clean(item.get("abstract")) or None
    if abstract and abstract.casefold().startswith("abstract "):
        abstract = abstract[9:].strip() or None
    text = f"{title} {abstract or ''}".casefold()
    return {
        "doi": doi[:255], "journal_key": journal["journal_key"],
        "journal_name": journal["name"][:255], "issn": issn,
        "title": title, "url": clean(item.get("URL")) or f"https://doi.org/{doi}",
        "authors": authors, "affiliations": affiliations,
        "abstract": abstract, "published_at": published_at,
        "year": int(published_at[:4]) if published_at else None,
        "volume": clean(item.get("volume"))[:64] or None,
        "issue": clean(item.get("issue"))[:64] or None,
        "pages": clean(item.get("page"))[:128] or None,
        "language": clean(item.get("language"))[:16] or None,
        "open_access": None,
        "cited_by_count": int(item["is-referenced-by-count"]) if item.get("is-referenced-by-count") is not None else None,
        "source_api": "crossref", "openalex_id": None,
        "matched_terms": [term for term in terms if term.casefold() in text],
    }


def fetch_openalex(issn, terms, mode, start, end, limit, timeout):
    records = []
    for term in (terms if mode == "keywords" else [None]):
        cursor = "*"
        while len(records) < limit:
            data = request_json(openalex_url(issn, term, mode, start, end, cursor), timeout)
            records.extend(work for work in data.get("results") or [] if isinstance(work, dict))
            cursor = (data.get("meta") or {}).get("next_cursor")
            if not cursor or len(records) >= limit:
                break
        if len(records) >= limit:
            break
    return records[:limit]


def fetch_crossref(issn, terms, mode, start, end, limit, timeout):
    records = []
    for term in (terms if mode == "keywords" else [None]):
        offset = 0
        while len(records) < limit:
            rows = min(100, limit - len(records))
            data = request_json(crossref_url(issn, term, mode, start, end, rows, offset), timeout)
            items = (data.get("message") or {}).get("items") or []
            records.extend(item for item in items if isinstance(item, dict))
            offset += rows
            if len(items) < rows or len(records) >= limit:
                break
        if len(records) >= limit:
            break
    return records[:limit]


def collect(request_data):
    parameters = request_data.get("parameters") or {}
    mode = parameters.get("collect_mode", "keywords")
    if mode not in {"keywords", "latest_issue"}:
        raise ValueError(f"unsupported collect_mode: {mode}")
    keys = list(dict.fromkeys(parameters.get("journal_keys") or DEFAULT_KEYS))
    if not keys:
        raise ValueError("journal_keys cannot be empty")
    limit = int(request_data["limit"])
    per_journal_limit = int(parameters.get("per_journal_limit", 50))
    lookback_days = int(parameters.get("lookback_days", 30))
    timeout = int(parameters.get("timeout_seconds", 20))
    require_abstract = bool(parameters.get("require_abstract", False))
    terms = requested_terms(request_data, parameters) if mode == "keywords" else []
    start, end = date_window(request_data, lookback_days)
    deadline = request_data.get("deadline_at", "")
    selected = [JOURNALS[key] for key in keys if key in JOURNALS]
    warnings = [
        {"code": "UNKNOWN_JOURNAL", "message": f"忽略未知期刊：{key}"}
        for key in keys if key not in JOURNALS
    ]
    items, seen, successful = [], set(), 0
    journal_count = len(selected)
    crossref_only = False
    for index, journal in enumerate(selected):
        if len(items) >= limit:
            break
        if deadline_reached(deadline):
            warnings.append({"code": "DEADLINE_REACHED", "message": "到达任务截止时间，已返回当前结果"})
            break
        journal_limit = min(per_journal_limit, limit // journal_count + int(index < limit % journal_count))
        if journal_limit <= 0:
            break
        issns = journal.get("issns") or [journal.get("issn")]
        issns = [value for value in dict.fromkeys(issns) if value]
        source_ok = False
        journal_items = []
        for issn in issns[:3]:
            try:
                if crossref_only:
                    raw = fetch_crossref(issn, terms, mode, start, end, journal_limit, timeout)
                    journal_items = [crossref_record(item, journal, issn, terms) for item in raw]
                else:
                    try:
                        raw = fetch_openalex(issn, terms, mode, start, end, journal_limit, timeout)
                        journal_items = [openalex_record(work, journal, issn, terms) for work in raw]
                    except SourceUnavailable:
                        crossref_only = True
                        raw = fetch_crossref(issn, terms, mode, start, end, journal_limit, timeout)
                        journal_items = [crossref_record(item, journal, issn, terms) for item in raw]
                source_ok = True
                if journal_items:
                    break
            except Exception as exc:
                warnings.append({
                    "code": "JOURNAL_REQUEST_FAILED",
                    "message": f"{journal['name']} ({issn})：{type(exc).__name__}: {exc}",
                })
                continue
        if not source_ok:
            continue
        successful += 1
        added = 0
        for item in journal_items:
            if not item:
                continue
            if require_abstract and not item["abstract"]:
                continue
            doi = item["doi"].casefold()
            if doi in seen:
                continue
            seen.add(doi)
            items.append(item)
            added += 1
            if added >= journal_limit or len(items) >= limit:
                break
        time.sleep(0.15)
    return items, warnings, successful


def write_output(output, execution_id, items, status, warnings, error=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    result = {
        "protocol_version": "1.0",
        "execution_id": execution_id,
        "status": status,
        "item_count": len(items),
        "next_cursor": None,
        "has_more": False,
        "warnings": warnings,
        "error": error,
    }
    temporary = output / "result.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output / "result.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request_data = json.loads(Path(args.request).read_text(encoding="utf-8"))
    output = Path(args.output)
    try:
        items, warnings, successful = collect(request_data)
        if not successful:
            write_output(output, request_data.get("execution_id", ""), [], "failed", warnings, {
                "code": "ALL_JOURNALS_FAILED",
                "message": "所有已选择期刊均未成功响应",
                "retryable": True,
            })
            return 1
        status = "partial" if warnings else "completed"
        write_output(output, request_data["execution_id"], items, status, warnings)
        return 0
    except Exception as exc:
        write_output(output, request_data.get("execution_id", ""), [], "failed", [], {
            "code": "PACKAGE_ERROR",
            "message": f"{type(exc).__name__}: {exc}",
            "retryable": False,
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
