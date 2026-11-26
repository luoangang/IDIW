from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import sys
import time
from urllib.error import HTTPError
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_RESPONSE = 3_000_000
JOURNAL_IDS = {"b11e9e7fdb08aa16": "ff007540-a7c7-4752-b593-efa08309babb"}
HTML_SITES = {"8298cc13a9e419b4", "350c066edebbda85"}
HTML_BASES = {"8298cc13a9e419b4": "https://www.aas.net.cn"}
SEARCH_DATA_SITES = {"912d94e870b17943": "cjg"}
ISSUE_TEXT = re.compile(r"((?:19|20)\d{2})\s*[,，年]\s*(?:\d+\s*[（(])?\s*(\d{1,2})\s*(?:[)）]|期)")
HTML_BLOCK_START = re.compile(r"<div\s+class=[\"']article-list[^\"']*[\"']\s+id=[\"']([^\"']*)[\"']", re.I)
RESNAME_BLOCK_START = re.compile(
    r"<h3\b[^>]*class=[\"'][^\"']*resName[^\"']*[\"'][^>]*>\s*<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.I | re.S,
)
SECTION_MARKER = re.compile(r"id=[\"'](onlineFirst|latestAcceptedList|latestAccepted|prepublish|current)[\"']", re.I)
ADVANCE_SECTIONS = {"onlineFirst", "latestAccepted", "latestAcceptedList"}
META_DC_DESCRIPTION = re.compile(r'<meta\b[^>]*name=["\']dc\.description["\'][^>]*>', re.I)
META_CONTENT = re.compile(r'content=["\']([^"\']*)["\']', re.I)
BLOCK_PAGE_MARKERS = ("安全验证", "人机验证", "滑动验证", "访问频繁", "请稍候", "请稍后再试")
ENRICH_RETRY_BACKOFF = 1.5


def read_response(opener, request, timeout):
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        encoding = (response.headers.get("Content-Encoding") or "").lower()
    if "gzip" in encoding:
        raw = gzip.decompress(raw)
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


PLACEHOLDER = re.compile(r"\{\{|\}\}")


def clean_abstract(value):
    text = clean(value)
    if not text or PLACEHOLDER.search(text):
        return None
    text = re.sub(r"^(?:摘\s*要|abstract)\s*[:：]\s*", "", text, flags=re.I)
    return text or None


def issue_from_text(value):
    """Extract (year, issue) from a citation label such as '2026, 43(11): 1-10'."""
    match = ISSUE_TEXT.search(clean(value))
    if not match:
        return None
    year, issue = int(match.group(1)), int(match.group(2))
    return (year, issue) if 1990 <= year <= 2100 and 1 <= issue <= 100 else None


def issue_from_record(record):
    year = str(record.get("year") or "")[:4]
    issue = record.get("issue") or record.get("issueNo") or record.get("period")
    issue_text = str(issue or "").strip()
    if year.isdigit() and issue_text.isdigit():
        key = (int(year), int(issue_text))
        return key if 1 <= key[1] <= 100 else None
    return issue_from_text(str(record.get("ppubDate") or record.get("publishDate") or ""))


def section_positions(page):
    return [(match.start(), match.group(1)) for match in SECTION_MARKER.finditer(page)]


def section_at(positions, offset):
    current = None
    for position, name in positions:
        if position > offset:
            break
        current = name
    return current


def restrict_latest_issue(items, warnings=None, journal_name=""):
    """Keep one issue only; advance/unassigned entries are dropped only when a current issue exists."""
    decorated = [(item, item.pop("_issue_key", None), item.pop("_issue_section", None)) for item in items]
    known = [key for _, key, _ in decorated if key is not None]
    latest = max(known) if known else None
    kept, stale, advance, unknown = [], 0, 0, 0
    for item, key, section in decorated:
        if key is not None:
            if latest is None or key == latest:
                kept.append(item)
            else:
                stale += 1
        elif latest is not None and section in ADVANCE_SECTIONS:
            advance += 1
        else:
            unknown += 1
            kept.append(item)
    if warnings is not None:
        if stale:
            warnings.append(f"{journal_name}: 过滤 {stale} 条非最新期次（最新 {latest[0]} 年第 {latest[1]} 期）")
        if advance:
            warnings.append(f"{journal_name}: 过滤 {advance} 条最新录用/网络首发（未排期）")
        if unknown:
            warnings.append(f"{journal_name}: {unknown} 条无法判定期次，已保留")
    return kept


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
        "abstract": clean_abstract(record.get("abstractinfoCn") or record.get("abstractinfoEn") or record.get("abstractinfo") or record.get("abstract")),
        "doi": doi[:255] or None, "year": int(year_raw) if year_raw.isdigit() else None,
    }


def parse_html_records(page, journal, warnings=None):
    matches = list(HTML_BLOCK_START.finditer(page))
    if not matches and not re.search(r"(?:没有找到|暂无相关|no results)", page, re.I):
        raise ValueError("UNSUPPORTED_TEMPLATE: no RHZH HTML article-list")
    base = HTML_BASES.get(journal["journal_key"], journal["url"]).rstrip("/")
    sections = section_positions(page)
    items = []
    for index, match in enumerate(matches):
        block = page[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(page)]
        article_id = match.group(1).strip()
        article_id_match = re.search(r"article_id=[\"']([^\"']+)[\"']", block[:300], re.I)
        if article_id_match:
            article_id = article_id_match.group(1)
        match_title = re.search(r'<div\s+class=["\']article-list-title[^"\']*["\'][^>]*>.*?<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, re.I | re.S)
        if not match_title:
            continue
        title = clean(match_title.group(2))
        if not title or "{{" in title or "}}" in title:
            continue
        if re.search(r"(?:目次|封面|封底|目录|稿约|征稿启事|投稿须知|编委会|编辑委员会|编后记)$", title):
            continue
        href = html.unescape(match_title.group(1))
        if "{{" in href or not re.search(r"(?:^|/)article/(?:id|doi)/", href, re.I):
            continue
        article_url = urljoin(base + "/", href)
        if not article_url.startswith(("http://", "https://")):
            continue
        doi_match = re.search(r"/article/doi/([^?#]+)", href, re.I)
        doi = doi_match.group(1) if doi_match else ""
        if not article_id:
            article_id = doi or hashlib.sha1(article_url.encode("utf-8")).hexdigest()[:16]
        authors = [clean(name) for name in re.findall(r'searchLike\(["\']authorNameCn["\'],["\']([^"\']+)', block, re.I)]
        time_match = re.search(r'class=["\']article-list-time[^"\']*["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        time_text = clean(time_match.group(1)) if time_match else ""
        year_match = re.search(r"\b(?:19|20)\d{2}\b", time_text)
        abstract_match = re.search(r'class=["\'][^"\']*search-abstract[^"\']*["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        item = {
            "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
            "journal_url": journal["url"], "external_id": article_id[:128],
            "title": title[:1000], "url": article_url,
            "authors": ", ".join(authors) or None,
            "abstract": clean_abstract(abstract_match.group(1)) if abstract_match else None,
            "doi": doi[:255] or None, "year": int(year_match.group(0)) if year_match else None,
        }
        item["_issue_key"] = issue_from_text(time_text)
        item["_issue_section"] = section_at(sections, match.start())
        items.append(item)
    if not items and matches:
        raise ValueError("UNSUPPORTED_TEMPLATE: only placeholder article-list entries")
    return restrict_latest_issue(items, warnings, journal["name"])


def parse_resname_records(page, journal, warnings=None):
    base = HTML_BASES.get(journal["journal_key"], journal["url"]).rstrip("/")
    matches = list(RESNAME_BLOCK_START.finditer(page))
    if not matches:
        raise ValueError("UNSUPPORTED_TEMPLATE: no RHZH resName article-list")
    items = []
    for index, match in enumerate(matches):
        block = page[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(page)]
        href = html.unescape(match.group(1))
        title = clean(match.group(2))
        if not title or "{{" in title:
            continue
        if re.search(r"(?:目次|封面|封底|目录|稿约|征稿启事|投稿须知|编委会|编辑委员会|编后记)$", title):
            continue
        article_url = urljoin(base + "/", href)
        if not article_url.startswith(("http://", "https://")):
            continue
        doi_match = re.search(r"/article/doi/([^?#]+)", href, re.I)
        doi = doi_match.group(1).rstrip("/") if doi_match else ""
        id_match = re.search(r"\bid:\s*(\d+)", block[:400])
        article_id = id_match.group(1) if id_match else (doi or hashlib.sha1(article_url.encode("utf-8")).hexdigest()[:16])
        authors_match = re.search(r'<em\b[^>]*class=["\'][^"\']*authors-text[^"\']*["\'][^>]*>(.*?)</em>', block, re.I | re.S)
        abstract_match = re.search(r'<em\b[^>]*class=["\'][^"\']*em-summary[^"\']*["\'][^>]*>(.*?)</em>', block, re.I | re.S)
        time_match = re.search(r'<span\b[^>]*class=["\'][^"\']*yearIssue[^"\']*["\'][^>]*>(.*?)</span>', block, re.I | re.S)
        time_text = clean(time_match.group(1)) if time_match else ""
        year_match = re.search(r"\b(?:19|20)\d{2}\b", time_text)
        items.append({
            "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
            "journal_url": journal["url"], "external_id": article_id[:128],
            "title": title[:1000], "url": article_url,
            "authors": (clean(authors_match.group(1)) or None) if authors_match else None,
            "abstract": clean_abstract(abstract_match.group(1)) if abstract_match else None,
            "doi": doi[:255] or None, "year": int(year_match.group(0)) if year_match else None,
            "_issue_key": issue_from_text(time_text),
            "_issue_section": "",
        })
    if not items:
        raise ValueError("UNSUPPORTED_TEMPLATE: only placeholder resName entries")
    return restrict_latest_issue(items, warnings, journal["name"])


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


def parse_current_data(raw, journal, warnings=None):
    payload = json.loads(raw)
    data = payload.get("data") if isinstance(payload, dict) else None
    articles = data.get("articles") if isinstance(data, dict) else None
    if articles is None and isinstance(payload, dict):
        articles = payload.get("articles")
    base = journal["url"].rstrip("/")
    items, seen = [], set()
    for record in articles or []:
        if not isinstance(record, dict):
            continue
        title = clean(record.get("titleCn") or record.get("title") or record.get("titleEn"))
        external_id = str(record.get("id") or record.get("file_no") or record.get("fileNo") or "").strip()
        if not title or not external_id or external_id in seen or PLACEHOLDER.search(title):
            continue
        if re.search(r"(?:目次|封面|封底|目录|稿约|征稿启事|投稿须知|编委会|编辑委员会|编后记)$", title):
            continue
        seen.add(external_id)
        raw_url = str(record.get("viewUrl") or record.get("url") or record.get("abstractUrl") or "").strip()
        doi = clean(record.get("doi"))
        if re.search(r"/article/(?:id|doi)/", raw_url, re.I):
            article_url = urljoin(base + "/", raw_url)
        elif doi:
            article_url = f"{base}/article/doi/{quote(doi, safe='/')}"
        elif external_id:
            article_url = f"{base}/article/id/{quote(external_id)}"
        else:
            article_url = base + "/"
        item = {
            "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
            "journal_url": journal["url"], "external_id": external_id[:128],
            "title": title[:1000], "url": article_url,
            "authors": clean(record.get("authors")) or None,
            "abstract": clean_abstract(record.get("abstractinfoCn") or record.get("abstractCn") or record.get("abstractinfoEn") or record.get("abstractinfo") or record.get("abstract")),
            "doi": doi[:255] or None,
            "year": int(record["year"]) if str(record.get("year") or "").isdigit() else None,
        }
        item["_issue_key"] = issue_from_record(record)
        item["_issue_section"] = "current"
        items.append(item)
    return restrict_latest_issue(items, warnings, journal["name"])


DETAIL_ABSTRACT_TAG = re.compile(r'<div\b[^>]*class=["\'][^"\']*(?<![\w-])article-abstract(?![\w-])[^"\']*["\'][^>]*>', re.I)
DIV_TAG = re.compile(r"<div\b[^>]*>|</div\s*>", re.I)


def balanced_div_html(page, start):
    depth = 1
    for match in DIV_TAG.finditer(page, start):
        if match.group(0).lower().startswith("</div"):
            depth -= 1
            if depth == 0:
                return page[start:match.start()]
        else:
            depth += 1
    return page[start:]


def extract_meta_abstract(page):
    for match in META_DC_DESCRIPTION.finditer(str(page or "")):
        content = META_CONTENT.search(match.group(0))
        if not content:
            continue
        abstract = clean_abstract(html.unescape(content.group(1)))
        if abstract:
            return abstract
    return None


def extract_detail_abstract(page):
    text = str(page or "")
    abstract = extract_meta_abstract(text)
    if abstract:
        return abstract
    for match in DETAIL_ABSTRACT_TAG.finditer(text):
        if PLACEHOLDER.search(match.group(0)):
            continue
        abstract = clean_abstract(balanced_div_html(text, match.end()))
        if abstract:
            return abstract
    return None


def is_blocked_page(page):
    text = str(page or "")
    return len(text) < 20000 and any(marker in text for marker in BLOCK_PAGE_MARKERS)


def fetch_detail_abstract(opener, item, timeout, referer=None):
    headers = {
        "User-Agent": USER_AGENT, "Accept": "text/html, application/xhtml+xml, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    page = read_response(opener, Request(item["url"], headers=headers), timeout)
    if is_blocked_page(page):
        return None, True
    return extract_detail_abstract(page), False


def enrich_abstract(opener, item, timeout, referer=None):
    if item.get("abstract") or not item.get("url"):
        return item
    try:
        abstract, _ = fetch_detail_abstract(opener, item, timeout, referer)
        if abstract:
            item["abstract"] = abstract
    except Exception:
        pass
    return item


def enrich_abstracts(opener, rows, timeout, limit, referer=None, delay=0.0, retries=1, sleeper=None):
    if limit <= 0:
        return rows
    sleep = sleeper or time.sleep
    attempts = 0
    for item in rows:
        if item.get("abstract") or not item.get("url"):
            continue
        if attempts >= limit:
            break
        attempts += 1
        for attempt in range(max(0, retries) + 1):
            wait = delay if attempt == 0 else delay * ENRICH_RETRY_BACKOFF
            if wait > 0:
                sleep(wait)
            try:
                abstract, blocked = fetch_detail_abstract(opener, item, timeout, referer)
            except Exception:
                continue
            if abstract:
                item["abstract"] = abstract
                break
            if not blocked:
                break
    return rows


def current_issue_items(opener, journal, timeout, warnings=None):
    explicit = journal.get("current_url")
    if explicit:
        try:
            if "current-data" in explicit:
                origin = urlsplit(explicit).scheme + "://" + urlsplit(explicit).netloc + "/"
                request = Request(explicit, data=b"", headers={
                    "User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*",
                    "X-Requested-With": "XMLHttpRequest", "Referer": origin,
                })
                text = read_response(opener, request, timeout)
                items = parse_current_data(text, journal, warnings)
            else:
                text = read_response(opener, Request(explicit, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,*/*"}), timeout)
                try:
                    items = parse_html_records(text, journal, warnings)
                except ValueError:
                    items = parse_resname_records(text, journal, warnings)
            if items:
                return items
        except Exception:
            pass
    base = HTML_BASES.get(journal["journal_key"], journal["url"]).rstrip("/")
    errors = []
    empty_ok = False
    for suffix in ("/cn/article/current", "/article/current", "/cn/article/latest"):
        try:
            request = Request(base + suffix, headers={"User-Agent": USER_AGENT, "Accept": "text/html, */*"})
            text = read_response(opener, request, timeout)
            try:
                items = parse_html_records(text, journal, warnings)
            except ValueError:
                items = parse_resname_records(text, journal, warnings)
            if items:
                return items
            empty_ok = True
        except (HTTPError, ValueError) as exc:
            errors.append(f"{suffix}: {exc}")
    if empty_ok:
        return []
    raise ValueError("UNSUPPORTED_TEMPLATE: " + "; ".join(errors))


def collect(request_data, journals):
    params = request_data.get("parameters") or {}
    mode = params.get("collect_mode", "keywords")
    if mode not in {"keywords", "latest_issue"}:
        raise ValueError(f"unsupported collect_mode: {mode}")
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
            if mode == "latest_issue":
                rows = current_issue_items(opener, journal, timeout, warnings)
                enrich_limit = int(params.get("abstract_enrich_limit", 5))
                if params.get("enrich_abstract", True) and enrich_limit > 0:
                    rows = enrich_abstracts(opener, rows, timeout, min(enrich_limit, per_journal), referer=journal["url"], delay=12.0)
                for item in rows:
                    if item["external_id"] in seen:
                        continue
                    seen.add(item["external_id"])
                    items.append(item)
                    if len(seen) >= per_journal or len(items) >= limit:
                        break
                successful += 1
                continue
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
