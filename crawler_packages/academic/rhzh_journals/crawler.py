from __future__ import annotations

import argparse
import html
import json
import re
import sys
from urllib.error import HTTPError
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_RESPONSE = 3_000_000
JOURNAL_IDS = {"b11e9e7fdb08aa16": "ff007540-a7c7-4752-b593-efa08309babb"}
HTML_SITES = {"8298cc13a9e419b4", "350c066edebbda85"}
HTML_BASES = {"8298cc13a9e419b4": "https://www.aas.net.cn"}
SEARCH_DATA_SITES = {"912d94e870b17943": "cjg"}


def read_response(opener, request, timeout):
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        return raw.decode("utf-8", errors="replace")


def search_page(opener, journal, query, page, timeout):
    base = journal["url"].rstrip("/")
    payload = {
        "searchWord": query, "searchField": "", "searchType": "0", "orderBy": "",
        "otherConditions": "", "analyzeWord": query, "actualSearchField": "",
        "language": "cn", "maxresult": "10", "currentpage": str(page),
    }
    journal_id = JOURNAL_IDS.get(journal["journal_key"])
    if journal_id:
        payload["journalId"] = journal_id
    request = Request(
        f"{base}/data/search/searchResult", data=urlencode(payload).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Referer": f"{base}/cn/search", "X-Requested-With": "XMLHttpRequest"},
    )
    data = json.loads(read_response(opener, request, timeout))
    pager = data.get("data", {}).get("pagerFilter") if isinstance(data, dict) and isinstance(data.get("data"), dict) else None
    if not isinstance(pager, dict) or not isinstance(pager.get("records"), list):
        raise ValueError("UNSUPPORTED_TEMPLATE: RHZH response lacks data.pagerFilter.records")
    return pager["records"]


def search_data_page(opener, journal, query, page, timeout):
    publisher = SEARCH_DATA_SITES[journal["journal_key"]]
    base = journal["url"].rstrip("/")
    payload = {
        "q": query, "publisherId": publisher, "language": "cn",
        "searchField": "titleCn;authors.authorNameCn;keywords.keywordCn;abstractinfoCn;doi",
        "searchType": "0", "highlightFields": "titleCn;authors.authorNameCn;abstractinfoCn",
        "filters": "[]", "sorts": "[]", "limit": "10", "pn": str(page),
    }
    request = Request(f"{base}/search-data", data=urlencode(payload).encode("utf-8"), headers={
        "User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Referer": base + "/",
    })
    data = json.loads(read_response(opener, request, timeout))
    rows = data.get("resultlist") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("UNSUPPORTED_TEMPLATE: search-data response lacks resultlist")
    if any(row.get("journalPublisherId") not in (None, publisher) for row in rows if isinstance(row, dict)):
        raise ValueError("search-data returned records for another journal")
    return rows


def clean(value):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"[\ue000-\uf8ff]", "", html.unescape(text))
    return " ".join(text.split())


def normalize(record, journal):
    if not isinstance(record, dict):
        return None
    title = clean(record.get("titleCn") or record.get("titleEn"))
    article_id = str(record.get("id") or "").strip()
    if not title or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", article_id) or "{{" in title:
        return None
    doi = clean(record.get("doi"))
    base = journal["url"].rstrip("/")
    prefix = "" if journal["journal_key"] in SEARCH_DATA_SITES else "/cn"
    article_url = f"{base}{prefix}/article/doi/{quote(doi, safe='/')}" if doi else f"{base}{prefix}/article/id/{quote(article_id)}"
    authors = record.get("authors") or []
    author_text = ", ".join(clean(author.get("authorNameCn") or author.get("authorNameEn")) for author in authors if isinstance(author, dict))
    year_raw = str(record.get("yearInt") or record.get("year") or "")[:4]
    return {
        "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
        "journal_url": journal["url"], "external_id": article_id[:128],
        "title": title[:1000], "url": article_url, "authors": author_text or None,
        "abstract": clean(record.get("abstractinfoCn") or record.get("abstractinfoEn") or record.get("abstractinfo") or record.get("abstract")) or None,
        "doi": doi[:255] or None, "year": int(year_raw) if year_raw.isdigit() else None,
    }


def parse_html_records(page, journal):
    blocks = re.split(r'<div\s+class=["\']article-list[^"\']*["\']\s+id=["\']([^"\']+)["\']', page, flags=re.I)
    if len(blocks) < 3 and not re.search(r"(?:没有找到|暂无相关|no results)", page, re.I):
        raise ValueError("UNSUPPORTED_TEMPLATE: no RHZH HTML article-list")
    base = HTML_BASES.get(journal["journal_key"], journal["url"]).rstrip("/")
    items = []
    for index in range(1, len(blocks), 2):
        article_id, block = blocks[index], blocks[index + 1]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", article_id):
            continue
        match = re.search(r'<div\s+class=["\']article-list-title[^"\']*["\'][^>]*>.*?<a\s+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, re.I | re.S)
        if not match:
            continue
        title = clean(match.group(2))
        if not title or "{{" in title or "}}" in title:
            continue
        href = html.unescape(match.group(1))
        if "{{" in href or not re.search(r"/article/(?:id|doi)/", href, re.I):
            continue
        article_url = urljoin(base + "/", href)
        if not article_url.startswith(("http://", "https://")):
            continue
        doi_match = re.search(r"/article/doi/([^?#]+)", href, re.I)
        doi = doi_match.group(1) if doi_match else ""
        authors = [clean(name) for name in re.findall(r'searchLike\(["\']authorNameCn["\'],["\']([^"\']+)', block, re.I)]
        time_match = re.search(r'class=["\']article-list-time[^"\']*["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        year_match = re.search(r"\b(?:19|20)\d{2}\b", clean(time_match.group(1))) if time_match else None
        abstract_match = re.search(r'class=["\'][^"\']*search-abstract[^"\']*["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        items.append({
            "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
            "journal_url": journal["url"], "external_id": article_id[:128],
            "title": title[:1000], "url": article_url,
            "authors": ", ".join(authors) or None,
            "abstract": clean(abstract_match.group(1)) if abstract_match else None,
            "doi": doi[:255] or None, "year": int(year_match.group(0)) if year_match else None,
        })
    if not items and len(blocks) >= 3:
        raise ValueError("UNSUPPORTED_TEMPLATE: only placeholder article-list entries")
    return items


def search_html_page(opener, journal, query, page, timeout):
    base = HTML_BASES.get(journal["journal_key"], journal["url"]).rstrip("/")
    payload = urlencode({"searchField": "titleCn", "q": query, "language": "cn", "page": page}).encode("utf-8")
    errors = []
    valid_empty = False
    for suffix in ("/cn/search", "/search"):
        request = Request(f"{base}{suffix}", data=payload, headers={
            "User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "text/html, */*", "Accept-Language": "zh-CN,zh;q=0.9", "Referer": base + "/",
        })
        try:
            text = read_response(opener, request, timeout)
            items = parse_html_records(text, journal)
            if items:
                return items
            valid_empty = True
        except (HTTPError, ValueError) as exc:
            errors.append(f"{suffix}: {exc}")
    if valid_empty:
        return []
    raise ValueError("UNSUPPORTED_TEMPLATE: " + "; ".join(errors))


def collect(request_data, journals):
    params = request_data.get("parameters") or {}
    keys = params.get("journal_keys", ["b11e9e7fdb08aa16"])
    query = request_data["query"].strip()
    if not keys or not query:
        raise ValueError("journal_keys and query must be nonempty")
    limit = request_data["limit"]
    per_journal = min(params.get("per_journal_limit", 20), max(1, (limit + len(keys) - 1) // len(keys)))
    timeout = params.get("timeout_seconds", 20)
    items, warnings, successful = [], [], 0
    for key in keys:
        if len(items) >= limit:
            break
        journal = journals.get(key)
        if not journal:
            warnings.append(f"Unknown journal key: {key}")
            continue
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        seen = set()
        try:
            for page in range(1, min(100, per_journal) + 1):
                if key in SEARCH_DATA_SITES:
                    rows = search_data_page(opener, journal, query, page, timeout)
                elif key in HTML_SITES:
                    rows = search_html_page(opener, journal, query, page, timeout)
                else:
                    try:
                        rows = search_page(opener, journal, query, page, timeout)
                    except HTTPError as exc:
                        if exc.code not in (404, 405):
                            raise
                        rows = search_html_page(opener, journal, query, page, timeout)
                    except ValueError as exc:
                        if "UNSUPPORTED_TEMPLATE" not in str(exc):
                            raise
                        rows = search_html_page(opener, journal, query, page, timeout)
                if not rows:
                    break
                previous_count = len(seen)
                for record in rows:
                    item = record if "journal_key" in record else normalize(record, journal)
                    if item and item["external_id"] not in seen:
                        seen.add(item["external_id"])
                        items.append(item)
                        if len(seen) >= per_journal or len(items) >= limit:
                            break
                if len(seen) >= per_journal or len(items) >= limit or len(seen) == previous_count:
                    break
            successful += 1
        except Exception as exc:
            warnings.append(f"{key} ({journal['name']}): {type(exc).__name__}: {exc}")
    return items, warnings, successful


def write_output(output, execution_id, items, status, warnings, error=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    result = {"protocol_version": "1.0", "execution_id": execution_id, "status": status, "item_count": len(items), "next_cursor": None, "has_more": False, "warnings": warnings, "error": error}
    temp = output / "result.json.tmp"
    temp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temp.replace(output / "result.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request_data = json.loads(Path(args.request).read_text(encoding="utf-8"))
    try:
        rows = json.loads(Path(__file__).with_name("journals.json").read_text(encoding="utf-8"))
        items, warnings, successful = collect(request_data, {row["journal_key"]: row for row in rows})
        status = "partial" if successful and warnings else "completed" if successful else "failed"
        error = None if successful else {"code": "ALL_JOURNALS_FAILED", "message": "; ".join(warnings)[:2000], "retryable": True}
        write_output(Path(args.output), request_data["execution_id"], items, status, warnings, error)
        return 0 if successful else 1
    except Exception as exc:
        write_output(Path(args.output), request_data.get("execution_id", ""), [], "failed", [], {"code": "CRAWLER_ERROR", "message": f"{type(exc).__name__}: {exc}", "retryable": False})
        return 1


if __name__ == "__main__":
    sys.exit(main())
