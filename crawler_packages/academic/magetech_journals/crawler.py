from __future__ import annotations

import argparse
import gzip
import hashlib
import html as html_lib
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener


@dataclass(frozen=True)
class Journal:
    key: str
    name: str
    base_url: str
    home_path: str
    journal_id: str = "1"
    current_url: str | None = None
    api_mode: str | None = None


DEFAULT_JOURNAL_KEYS = ["data_analysis", "lis", "qbzl"]
BUILTIN_JOURNALS = {
    "data_analysis": Journal(
        "data_analysis", "数据分析与知识发现",
        "https://manu44.magtech.com.cn/Jwk_infotech_wk3", "/CN/home",
    ),
    "lis": Journal(
        "lis", "图书情报工作",
        "https://www.lis.ac.cn", "/CN/0252-3116/home.shtml",
    ),
    "qbzl": Journal(
        "qbzl", "情报资料工作",
        "http://qbzl.ruc.edu.cn", "/CN/1002-0314/home.shtml",
    ),
}


def journal_from_catalog(row: dict) -> Journal:
    parsed = urlsplit(row["url"])
    path = parsed.path.rstrip("/")
    cn_at = path.lower().find("/cn/")
    if cn_at >= 0:
        base_path = path[:cn_at]
        home_path = path[cn_at:]
    elif path.lower() == "/cn":
        base_path, home_path = "", "/CN/home"
    else:
        base_path, home_path = path, "/CN/home"
    base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}"
    key = "qbzl" if row["name"] == "情报资料工作" and parsed.hostname == "qbzl.ruc.edu.cn" else row["journal_key"]
    return Journal(key, row["name"], base_url, home_path, current_url=row.get("current_url"), api_mode=row.get("api_mode"))


def load_journals() -> dict[str, Journal]:
    rows = json.loads(Path(__file__).with_name("journals.json").read_text(encoding="utf-8"))
    journals = dict(BUILTIN_JOURNALS)
    for row in rows:
        journal = journal_from_catalog(row)
        journals.setdefault(journal.key, journal)
        if journal.key != row["journal_key"]:
            journals[row["journal_key"]] = journals[journal.key]
    return journals


JOURNALS = load_journals()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html_lib.unescape(value).replace("\xa0", " ")).strip()


def safe_term(value: str) -> str:
    value = re.sub(r"[\[\](){}\r\n\x00-\x1f]", " ", value or "")
    return re.sub(r"\s+", " ", value).strip()[:200]


def search_sql(term: str, journal_id: str, page: int) -> str:
    fields = ["Title", "Abstract", "Keyword", "Author", "AuthorCompany", "DOI"]
    expression = f"{term}[{fields[0]}]"
    for field in fields[1:]:
        expression = f"({expression}) OR {term}[{field}]"
    base = f"({expression}) AND {journal_id}[Journal]"
    return base if page == 1 else f"({base} AND {page}[Pager])"


def decode_response(response) -> str:
    charset = response.headers.get_content_charset() or "utf-8"
    raw = response.read()
    encoding = (response.headers.get("Content-Encoding") or "").lower()
    if raw.startswith(b"\x1f\x8b") or "gzip" in encoding:
        raw = gzip.decompress(raw)
    return raw.decode(charset, errors="replace")


def post_search(opener, journal: Journal, term: str, page: int, timeout: int = 25) -> str:
    url = f"{journal.base_url}/CN/article/advancedSearchResult.do"
    payload = urlencode({"searchSQL": search_sql(term, journal.journal_id, page), "ajax": "true"}).encode()
    request = Request(
        url, data=payload,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": journal.base_url.rstrip("/") + journal.home_path},
    )
    with opener.open(request, timeout=timeout) as response:
        return decode_response(response)


GENERIC_CURRENT_URLS = {
    "72e1e50d662fbc78": "http://cjarrp.ijournals.cn/zgnyzyyqh/ch/reader/issue_list.aspx?year_id=2026&quarter_id=9",
    "ead9e7ee5c315dd0": "http://www.cjig.cn/zh/issue/2026/11/",
    "80b225e7cb60f04a": "https://www.teleonline.cn/dxjs/ch/reader/issue_list.aspx?year_id=2026&quarter_id=10",
}


def current_issue_url(journal: Journal) -> str:
    return journal.current_url or GENERIC_CURRENT_URLS.get(journal.key, f"{journal.base_url}/CN/current")


def fetch_current_issue(opener, journal: Journal, timeout: int = 25) -> str:
    request = Request(
        current_issue_url(journal),
        headers={**HEADERS, "Referer": journal.base_url.rstrip("/") + journal.home_path},
    )
    with opener.open(request, timeout=timeout) as response:
        return decode_response(response)


MAX_LATEST_ISSUE_PAGES = 20
PAGE_QUERY_NAMES = {"page", "pageno", "pagenum"}
PAGER_EXTRA_QUERY_NAMES = {"totalpage", "pagesize", "ajax", "pages", "_"}


def anchor_links(document: str):
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", document, re.I | re.S):
        href = re.search(r'href\s*=\s*["\']([^"\']+)["\']', match.group(1), re.I)
        if href:
            yield html_lib.unescape(href.group(1)).strip(), clean_html(match.group(2))


def page_number_from_url(url: str):
    for key, values in parse_qs(urlsplit(url).query, keep_blank_values=True).items():
        if key.lower() not in PAGE_QUERY_NAMES:
            continue
        value = (values or [""])[0].strip()
        if value.isdigit() and 1 <= int(value) <= 999:
            return int(value)
    return None


def same_issue_link(base_url: str, candidate: str) -> bool:
    """True when candidate is a pager URL of the same document on the same host/path.

    Issue/year selectors present on the entry URL must keep their value, and extra
    query keys beyond pager bookkeeping are rejected, so cross-issue links are never
    mistaken for page 2..N.
    """
    base, target = urlsplit(base_url), urlsplit(candidate)
    if target.scheme not in {"http", "https"}:
        return False
    if target.netloc.lower() != base.netloc.lower():
        return False
    if (target.path.rstrip("/") or "/") != (base.path.rstrip("/") or "/"):
        return False
    base_query = dict(parse_qsl(base.query, keep_blank_values=True))
    target_query = dict(parse_qsl(target.query, keep_blank_values=True))
    for key, value in target_query.items():
        lowered = key.lower()
        if lowered in PAGE_QUERY_NAMES or lowered in PAGER_EXTRA_QUERY_NAMES:
            continue
        if base_query.get(key) != value:
            return False
    for key, value in base_query.items():
        if key.lower() in PAGE_QUERY_NAMES:
            continue
        if target_query.get(key) != value:
            return False
    return True


def discover_pager_pages(document: str, base_url: str, max_pages: int) -> dict[int, str]:
    """Numeric pager / next-page links of the same host+path, numbered 2..max_pages."""
    pages: dict[int, str] = {}
    base_without_fragment = base_url.split("#", 1)[0]
    for href, text in anchor_links(document):
        url = urljoin(base_url, href)
        number = page_number_from_url(url)
        if number is None and re.fullmatch(r"\d{1,3}", text or ""):
            number = int(text)
        if number is None or number < 2 or number > max_pages:
            continue
        if url.split("#", 1)[0] == base_without_fragment:
            continue
        if not same_issue_link(base_url, url):
            continue
        pages.setdefault(number, url)
    return pages


ISSUE_MARKER_PATTERNS = (
    re.compile(r"(20\d{2})\s*年\s*(?:第\s*)?(\d{1,2})\s*期"),
    re.compile(r"第\s*(\d{1,2})\s*期"),
    re.compile(r"Vol(?:ume)?\.?\s*(\d+)\s*[,，]?\s*(?:No|Issue)\.?\s*(\d+)", re.I),
)


def extract_issue_marker(document: str):
    for pattern in ISSUE_MARKER_PATTERNS:
        match = pattern.search(document)
        if match:
            return "-".join(group for group in match.groups() if group)
    return None


def fetch_toc_page(opener, journal: Journal, url: str, timeout: int = 25) -> str:
    request = Request(
        url,
        headers={**HEADERS, "Referer": current_issue_url(journal)},
    )
    with opener.open(request, timeout=timeout) as response:
        return decode_response(response)


LEGACY_ABSTRACT_LINK = re.compile(
    r'href\s*=\s*["\']((?:\.\./|/)?abstract/abstract(\d+)\.shtml)["\']', re.I
)
LEGACY_BIBLIOGRAPHY = re.compile(
    r"(19\d{2}|20\d{2})\s*Vol\.?\s*(\d+)\s*\(\s*(\d+)\s*\)\s*[:：]\s*(\d+)"
    r"(?:\s*[-–—]\s*(\d+))?",
    re.I,
)


def parse_legacy_table_items(document: str, journal: Journal) -> list[dict]:
    """Old Magtech TOC tables: `TD.J_VM` page/author rows plus `CN/abstract/abstractN.shtml`."""
    records = []
    for block in re.split(r"<TABLE\b", document, flags=re.I):
        link = LEGACY_ABSTRACT_LINK.search(block)
        if not link:
            continue
        title_match = re.search(r"<b>\s*(.*?)\s*</b>", block, re.I | re.S)
        bibliography = LEGACY_BIBLIOGRAPHY.search(html_lib.unescape(block))
        if not title_match or not bibliography:
            continue
        title = clean_html(title_match.group(1))
        pages = "-".join(part for part in (bibliography.group(4), bibliography.group(5)) if part)
        if not title or re.fullmatch(r"0+\s*-\s*0+", pages):
            continue
        if re.search(r"(目录|封面|封底|目次)$", title):
            continue
        cells = re.findall(
            r'<td\b[^>]*class\s*=\s*["\'][^"\']*J_VM[^"\']*["\'][^>]*>(.*?)</td>',
            block, re.I | re.S,
        )
        authors = []
        if cells and re.fullmatch(r"\d+", clean_html(cells[0])) and len(cells) > 1:
            authors = [value.strip() for value in re.split(r"[,，;；、]+", clean_html(cells[1])) if value.strip()]
        if not authors:
            for cell in cells:
                text = clean_html(cell)
                if text and not re.search(r"Vol\.|\bdoi\b|^\d+$", text, re.I) and re.search(r"[,，;；、]", text):
                    authors = [value.strip() for value in re.split(r"[,，;；、]+", text) if value.strip()]
                    break
        doi_match = re.search(r'\bdoi\s*[:：]\s*(10\.\d{4,9}/[^\s<"\']+)', html_lib.unescape(block), re.I)
        pdf_match = re.search(
            r'href\s*=\s*["\']([^"\']*downloadArticleFile\.do\?attachType=PDF[^"\']*)["\']',
            block, re.I,
        )
        records.append({
            "journal_key": journal.key,
            "journal_name": journal.name,
            "external_id": link.group(2),
            "title": title[:1000],
            "url": urljoin(current_issue_url(journal), html_lib.unescape(link.group(1))),
            "authors": authors,
            "abstract": None,
            "doi": doi_match.group(1).rstrip(".,;，；") if doi_match else None,
            "year": int(bibliography.group(1)),
            "volume": bibliography.group(2) or None,
            "issue": bibliography.group(3) or None,
            "pages": pages[:64],
            "pdf_url": (
                urljoin(current_issue_url(journal), html_lib.unescape(pdf_match.group(1)))
                if pdf_match else None
            ),
            "source_site": "magetech",
        })
    return ensure_unique_external_ids(records)


def parse_toc_document(document: str, journal: Journal) -> list[dict]:
    try:
        page_items = parse_search_result(document, journal)
    except ValueError:
        page_items = []
    if not page_items and LEGACY_ABSTRACT_LINK.search(document) and re.search(
        r'class\s*=\s*["\'][^"\']*J_VM', document, re.I
    ):
        page_items = parse_legacy_table_items(document, journal)
    generic_items = parse_generic_toc(document, journal)
    if not page_items or (len(generic_items) > len(page_items) and len(page_items) < 3):
        page_items = generic_items
    return page_items


def fetch_latest_issue(opener, journal: Journal, max_pages: int, deadline, delay: float,
                       warnings: list, timeout: int = 25) -> list[dict]:
    """Entry page plus any same-issue numeric pager pages, merged with one parser."""
    entry_url = current_issue_url(journal)
    document = fetch_current_issue(opener, journal, timeout)
    page_items = list(parse_toc_document(document, journal))
    page_cap = max(0, min(int(max_pages), MAX_LATEST_ISSUE_PAGES))
    pager = discover_pager_pages(document, entry_url, page_cap) if page_cap > 1 else {}
    if not pager:
        return page_items
    entry_marker = extract_issue_marker(document)
    known = {item["external_id"] for item in page_items}
    for number in sorted(pager):
        if datetime.now(timezone.utc) >= deadline:
            warnings.append({"code": "DEADLINE_REACHED", "message": "到达任务截止时间，已返回当前结果"})
            break
        if delay:
            time.sleep(delay)
        try:
            page_document = fetch_toc_page(opener, journal, pager[number], timeout)
        except Exception as exc:
            warnings.append({
                "code": "PAGINATION_PAGE_FAILED",
                "message": f"{journal.name} 当期第 {number} 页请求失败：{type(exc).__name__}: {exc}",
            })
            break
        page_marker = extract_issue_marker(page_document)
        if entry_marker and page_marker and entry_marker != page_marker:
            warnings.append({
                "code": "ISSUE_MARKER_MISMATCH",
                "message": f"{journal.name} 第 {number} 页期次（{page_marker}）与当期（{entry_marker}）不一致，已停止翻页",
            })
            break
        added = 0
        for item in parse_toc_document(page_document, journal):
            if item["external_id"] in known:
                continue
            known.add(item["external_id"])
            page_items.append(item)
            added += 1
        if added == 0:
            warnings.append({
                "code": "PAGINATION_STALLED",
                "message": f"{journal.name} 当期第 {number} 页未返回新的去重文章，已停止翻页",
            })
            break
    return page_items


STAE_KEY = "0da5df72000d4e9f"
STAE_PAGE_SIZE = 200
STAE_FALLBACK_PAGE_SIZE = 50
STAE_MAX_PAGES = 20


def read_json_response(opener, url: str, timeout: int):
    request = Request(url, headers={**HEADERS, "Accept": "application/json"})
    with opener.open(request, timeout=timeout) as response:
        return json.loads(decode_response(response))


def fetch_stae_current(opener, journal: Journal, timeout: int = 25, warnings: list | None = None) -> list[dict]:
    base = journal.base_url.rstrip("/")
    current = read_json_response(opener, f"{base}/CN/api/site/data/article/current", timeout)
    issue = (current or {}).get("data") or {}
    issue_id = issue.get("id")
    if not issue_id:
        raise ValueError("STAE current issue id missing")
    page_size = STAE_PAGE_SIZE
    records: list[dict] = []
    seen_ids: set[str] = set()
    total = None
    for page_num in range(1, STAE_MAX_PAGES + 1):
        list_url = (
            f"{base}/CN/api/site/data/article/fast/getArticleList"
            f"?issueId={issue_id}&pageSize={page_size}&pageNum={page_num}"
            f"&orderBy=start_page&orderType=asc"
        )
        try:
            payload = read_json_response(opener, list_url, timeout)
        except Exception:
            if page_size <= STAE_FALLBACK_PAGE_SIZE:
                raise
            page_size = STAE_FALLBACK_PAGE_SIZE
            list_url = (
                f"{base}/CN/api/site/data/article/fast/getArticleList"
                f"?issueId={issue_id}&pageSize={page_size}&pageNum={page_num}"
                f"&orderBy=start_page&orderType=asc"
            )
            payload = read_json_response(opener, list_url, timeout)
            if warnings is not None:
                warnings.append({
                    "code": "STAE_PAGE_SIZE_FALLBACK",
                    "message": f"{journal.name} 大 pageSize 请求失败，已回退到 {page_size} 条/页",
                })
        data = (payload or {}).get("data") or {}
        chunk = data.get("data") or []
        if total is None:
            total = data.get("total") if data.get("total") is not None else (payload or {}).get("total")
        added = 0
        for record in chunk:
            if not isinstance(record, dict):
                continue
            record_id = str(record.get("id") or "")
            if record_id and record_id in seen_ids:
                continue
            if record_id:
                seen_ids.add(record_id)
            records.append(record)
            added += 1
        if not chunk:
            break
        if total is not None and len(records) >= int(total):
            break
        if added == 0:
            if warnings is not None:
                warnings.append({
                    "code": "STAE_PAGINATION_STALLED",
                    "message": f"{journal.name} 第 {page_num} 页未返回新文章，已停止翻页",
                })
            break
        if total is None and len(chunk) < page_size:
            break
        if page_num == STAE_MAX_PAGES and warnings is not None:
            warnings.append({
                "code": "STAE_PAGINATION_LIMIT",
                "message": f"{journal.name} 当期达到 {STAE_MAX_PAGES} 页上限，可能未取全",
            })
    if total is None and page_size and len(records) == page_size and warnings is not None:
        warnings.append({
            "code": "STAE_PAGE_TRUNCATED",
            "message": f"{journal.name} 当期返回条数等于 pageSize={page_size} 且无 total，可能被截断",
        })
    year = str(issue.get("year") or "")
    issue_no = str(issue.get("issue") or "")
    result = []
    for record in records:
        if not isinstance(record, dict):
            continue
        title = clean_html(record.get("titleCn") or record.get("titleEn"))
        article_id = str(record.get("id") or "").strip()
        if not title or not article_id:
            continue
        doi = str(record.get("doi") or "").strip() or None
        abstract = clean_html(record.get("abstractCn") or record.get("abstractEn")) or None
        authors = [part.strip() for part in re.split(r"[,，;；、]+", str(record.get("authorsListCn") or "")) if part.strip()]
        result.append({
            "journal_key": journal.key,
            "journal_name": journal.name,
            "external_id": article_id,
            "title": title,
            "url": f"https://doi.org/{doi}" if doi else f"{base}/CN/article/abstract/{article_id}",
            "authors": authors,
            "abstract": abstract,
            "doi": doi,
            "year": int(year) if year.isdigit() else None,
            "volume": str(issue.get("volume") or "") or None,
            "issue": f"{year}年第{issue_no}期" if year and issue_no else None,
            "pages": f"{record.get('startPage')}-{record.get('endPage')}" if record.get("startPage") and record.get("endPage") else None,
            "pdf_url": None,
            "source_site": base,
        })
    return result


def parse_generic_toc(page: str, journal: Journal) -> list[dict]:
    current_url = current_issue_url(journal)
    issue_match = re.search(r"(?:year_id=|/issue/)(20\d{2})[^0-9]*(?:quarter_id=|/)(\d+)", current_url, re.I)
    issue = f"{issue_match.group(1)}年第{issue_match.group(2)}期" if issue_match else None
    items, seen = [], set()
    for href, text in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.I | re.S):
        title = clean_html(text)
        link = urljoin(current_url, html_lib.unescape(href).strip())
        if not title or len(title) < 8 or not re.search(
            r"view_abstract\.aspx\?|/zh/article/doi/|/CN/Y\d{4}/V\d+/I\d+/\d+|"
            r"/CN/10\.\d{4,9}(?:[./-][^/?#]+)+|abstract/abstract\d+\.shtml",
            link, re.I
        ):
            continue
        if re.search(r"^(首页|上一页|下一页|更多|过刊|当期|本期|目录|登录|注册|封面|封底|版权|投稿须知)", title):
            continue
        if re.match(r"^(?:20\d{2}[-年]\d{1,2}月?)?目录$", title):
            continue
        if re.search(r"封面(?:和|与)?目次\s*$", title):
            continue
        file_no = re.search(r"[?&]file_no=([^&]+)", link, re.I)
        doi_match = re.search(r"/doi/(10\.\d{4,9}/[^/?#]+)", link, re.I)
        cn_doi = re.search(r"/CN/(10\.\d{4,9}(?:[./-][^/?#]+)+)", link, re.I)
        path_id = re.search(r"/CN/(Y\d{4}/V[^/?#]*/I[^/?#]*/\d+)", link, re.I)
        abstract_id = re.search(r"abstract/abstract(\d+)\.shtml", link, re.I)
        external_id = (file_no.group(1) if file_no else (doi_match.group(1) if doi_match else
                      (cn_doi.group(1) if cn_doi else (path_id.group(1) if path_id else
                       (abstract_id.group(1) if abstract_id else None)))))
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        doi = doi_match.group(1) if doi_match else (cn_doi.group(1) if cn_doi else None)
        year_match = re.search(r"(20\d{2})", external_id or "")
        items.append({
            "journal_key": journal.key,
            "journal_name": journal.name,
            "external_id": external_id,
            "title": title[:1000],
            "url": link,
            "authors": [],
            "abstract": None,
            "doi": doi,
            "year": int(year_match.group(1)) if year_match else None,
            "volume": None,
            "issue": issue,
            "pages": None,
            "pdf_url": None,
            "source_site": journal.base_url,
        })
    return items


def parse_bibliography(block: str):
    match = re.search(r'class=["\']j-volumn["\'][^>]*>(.*?)</span>', block, re.I | re.S)
    text = clean_html(match.group(1)) if match else ""
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else None
    detail = re.search(
        r"\b(?:19\d{2}|20\d{2})\s*[,，]\s*([^\s,(，]+)\s*[（(]\s*([^）)]+?)\s*[）)]\s*[:：]\s*(\d+(?:\s*[-–—]\s*\d+)?)",
        text,
    )
    if not detail:
        return year, None, None, None
    return year, detail.group(1).strip(), detail.group(2).strip(), re.sub(r"\s*[-–—]\s*", "-", detail.group(3))


def parse_items(document: str, journal: Journal) -> list[dict]:
    segments = re.split(r'<li\s+id=["\']art(\d+)["\']\s+class=["\']noselectrow["\']', document, flags=re.I)
    records = []
    for index in range(1, len(segments) - 1, 2):
        article_id, block = segments[index].strip(), segments[index + 1]
        title_area = re.search(r'<div[^>]+class=["\'][^"\']*j-title[^"\']*["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        area = title_area.group(1) if title_area else block
        link = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', area, re.I | re.S)
        if not link:
            continue
        title = clean_html(link.group(2))
        if not title:
            continue
        url = urljoin(journal.base_url + "/", html_lib.unescape(link.group(1)).strip())
        doi_match = re.search(r'(?:doi\.org/|/CN/)(10\.\d{4,9}/[^"\'<>\s]+)', block, re.I)
        doi = html_lib.unescape(doi_match.group(1)).rstrip(".,;，；") if doi_match else None
        author_match = re.search(r'class=["\']j-author["\'][^>]*>\s*(.*?)\s*</div>', block, re.I | re.S)
        author_text = clean_html(author_match.group(1)) if author_match else ""
        authors = [part.strip() for part in re.split(r"[,，;；、]+", author_text) if part.strip()]
        abstract_match = re.search(r'class=["\']j-abstract["\'][^>]*>\s*(.*?)\s*</div>', block, re.I | re.S)
        abstract = clean_html(abstract_match.group(1)) if abstract_match else None
        year, volume, issue, pages = parse_bibliography(block)
        pdf_match = re.search(r"lsdy1\('PDF','(\d+)'", block)
        pdf_url = (
            f"{journal.base_url}/CN/article/downloadArticleFile.do?attachType=PDF&id={pdf_match.group(1)}"
            if pdf_match else (f"{journal.base_url}/CN/PDF/{doi}" if doi else None)
        )
        records.append({
            "journal_key": journal.key,
            "journal_name": journal.name,
            "external_id": article_id,
            "title": title,
            "url": url,
            "authors": authors,
            "abstract": abstract or None,
            "doi": doi,
            "year": year,
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "pdf_url": pdf_url,
            "source_site": "magetech",
        })
    return ensure_unique_external_ids(records)


def ensure_unique_external_ids(records: list[dict]) -> list[dict]:
    """Keep unique article ids; fall back to DOI or URL hash when the site repeats ids."""
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.get("external_id") or "")
        counts[key] = counts.get(key, 0) + 1
    used: set[str] = set()
    for record in records:
        key = str(record.get("external_id") or "")
        if key and counts[key] == 1 and key not in used:
            used.add(key)
            continue
        doi = str(record.get("doi") or "").strip()
        if doi:
            candidate = doi
        else:
            candidate = "url-" + hashlib.sha1(str(record.get("url") or "").encode("utf-8")).hexdigest()[:16]
        base, suffix = candidate[:255], 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        record["external_id"] = candidate[:255]
        used.add(record["external_id"])
    return records


def parse_old_items(document: str, journal: Journal) -> list[dict]:
    segments = re.split(
        r'<div\b(?=[^>]*\bid=["\']?art(\d+)["\']?)(?=[^>]*\bclass=["\']?noselectrow["\']?)[^>]*>',
        document, flags=re.I,
    )
    records = []
    for index in range(1, len(segments) - 1, 2):
        article_id, block = segments[index].strip(), segments[index + 1]
        title_link = re.search(
            r'<a\b(?=[^>]*\bclass=["\']txt_biaoti["\'])(?=[^>]*\bhref=["\']([^"\']+)["\'])[^>]*>(.*?)</a>',
            block, re.I | re.S,
        )
        if not title_link:
            continue
        title = clean_html(title_link.group(2))
        if not title:
            continue
        url = urljoin(journal.base_url + "/", html_lib.unescape(title_link.group(1)))
        authors_match = re.search(r'class=["\']abs_zuozhe(?:_cn)?["\'][^>]*>(.*?)</span>', block, re.I | re.S)
        authors = [value.strip() for value in re.split(r"[,，;；、]+", clean_html(authors_match.group(1))) if value.strip()] if authors_match else []
        abstract_match = re.search(
            rf'id=["\']Abstract{re.escape(article_id)}["\'][^>]*class=["\']white_content["\'][^>]*>(.*?)</div>',
            block, re.I | re.S,
        )
        bibliography_match = re.search(r'class=["\']abs_njq["\'][^>]*>(.*?)</span>', block, re.I | re.S)
        bibliography = clean_html(bibliography_match.group(1)) if bibliography_match else ""
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", bibliography)
        detail = re.search(r"\b(?:19\d{2}|20\d{2})\s*[,，]\s*([^\s(（]+)\s*[（(]([^）)]+)[）)]\s*[:：]\s*([\d\s-]+)", bibliography)
        doi_match = re.search(r"(10\.\d{4,9}/[^\s\"'<>]+)", url)
        records.append({
            "journal_key": journal.key, "journal_name": journal.name,
            "external_id": article_id, "title": title, "url": url,
            "authors": authors, "abstract": clean_html(abstract_match.group(1)) if abstract_match else None,
            "doi": doi_match.group(1) if doi_match else None,
            "year": int(year_match.group(1)) if year_match else None,
            "volume": detail.group(1)[:64] if detail else None,
            "issue": detail.group(2)[:64] if detail else None,
            "pages": detail.group(3).strip()[:64] if detail else None,
            "pdf_url": None, "source_site": "magetech",
        })
    return ensure_unique_external_ids(records)


def parse_cma_items(document: str, journal: Journal) -> list[dict]:
    link_pattern = re.compile(
        r'<a\b(?=[^>]*class=["\'][^"\']*\blunwen\b)(?=[^>]*href=["\']([^"\']+)["\'])[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    records = []
    for match in link_pattern.finditer(document):
        href = html_lib.unescape(match.group(1)).strip()
        if "/CN/10.3877/" not in href:
            continue
        title = clean_html(match.group(2))
        if not title:
            continue
        url = urljoin(journal.base_url + "/", href)
        external_id = href.split("/CN/")[-1][:255]
        window = document[max(0, match.start() - 800): match.end() + 800]
        authors_match = re.search(
            r'class=["\'][^"\']*zuozhe[^"\']*["\'][^>]*>(.*?)</', window, re.I | re.S
        )
        authors = (
            [value.strip() for value in re.split(r"[,，;；、]+", clean_html(authors_match.group(1))) if value.strip()]
            if authors_match else []
        )
        doi_match = re.search(r"(10\.\d{4,9}/[^\s\"'<>]+)", url)
        issue_match = re.search(r"\.(20\d{2})\.(\d{2})\.(\d{3})(?:$|[?#])", href)
        records.append({
            "journal_key": journal.key,
            "journal_name": journal.name,
            "external_id": external_id,
            "title": title,
            "url": url,
            "authors": authors,
            "abstract": None,
            "doi": doi_match.group(1) if doi_match else None,
            "year": int(issue_match.group(1)) if issue_match else None,
            "volume": None,
            "issue": issue_match.group(2) if issue_match else None,
            "pages": issue_match.group(3) if issue_match else None,
            "pdf_url": None,
            "source_site": "magetech",
        })
    return ensure_unique_external_ids(records)


def parse_search_result(document: str, journal: Journal) -> list[dict]:
    if "/CN/10.3877/" in document and re.search(r'class=["\'][^"\']*\blunwen\b', document, re.I):
        return parse_cma_items(document, journal)
    if re.search(r'<li\b(?=[^>]*\bid=["\']art\d+["\'])(?=[^>]*\bclass=["\']noselectrow["\'])', document, re.I):
        return parse_items(document, journal)
    if re.search(r'<div\b(?=[^>]*\bid=["\']?art\d+["\']?)(?=[^>]*\bclass=["\']?noselectrow["\']?)', document, re.I):
        return parse_old_items(document, journal)
    if re.search(r"没有找到|未检索到|检索结果\s*0|共\s*0\s*条|no\s+results?", document, re.I):
        return []
    raise ValueError("UNSUPPORTED_TEMPLATE: no recognized Magtech search result markup")


ABSTRACT_END_PATTERN = re.compile(
    r"(?:\bAbstract\b|\bABSTRACT\b|\bKey\s*wor(?:d|ds)\b|\bKeywords?\b|"
    r"关键词|关键字|【关键词】|参考文献|引用本文|\bReferences\b|\bREFERENCES\b)"
)
ABSTRACT_LABEL_PATTERN = re.compile(r"^(?:摘\s*要|【摘\s*要】|\[摘\s*要\])\s*[:：]?\s*")
ABSTRACT_MIN_LENGTH = 30
ABSTRACT_MAX_LENGTH = 4000


def attr_value(tag_text: str, attr_name: str):
    match = re.search(rf'\b{attr_name}\s*=\s*["\']([^"\']*)["\']', tag_text, re.I)
    return match.group(1) if match else None


def tag_has_attr(tag_text: str, attr_name: str, value: str, exact: bool = True) -> bool:
    current = attr_value(tag_text, attr_name)
    if current is None:
        return False
    if exact:
        return current.strip() == value
    return value in current.split()


def element_inner_html(document: str, tag: str, matcher) -> str | None:
    """Inner HTML of the first `<tag ...>` whose opening tag satisfies matcher."""
    start = None
    for match in re.finditer(rf"<{tag}\b[^>]*>", document, re.I):
        if matcher(match.group(0)):
            start = match
            break
    if start is None:
        return None
    depth = 1
    for token in re.finditer(rf"<(/?){tag}\b[^>]*>", document[start.end():], re.I):
        if token.group(1):
            depth -= 1
            if depth == 0:
                return document[start.end(): start.end() + token.start()]
        else:
            depth += 1
    return document[start.end():]


def html_to_text(block: str) -> str:
    value = re.sub(r"<(script|style)\b.*?</\1>", " ", block or "", flags=re.I | re.S)
    value = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>|</table>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html_lib.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def clean_abstract_text(text: str) -> str | None:
    if not text:
        return None
    value = re.sub(r"\s+", " ", text).strip()
    value = ABSTRACT_LABEL_PATTERN.sub("", value)
    end = ABSTRACT_END_PATTERN.search(value)
    if end and end.start() >= 20:
        value = value[:end.start()]
    value = re.sub(r"\s+", " ", value).strip(" :：;；,，.。、-")
    if len(value) < ABSTRACT_MIN_LENGTH:
        return None
    return value[:ABSTRACT_MAX_LENGTH]


def extract_detail_abstract(document: str) -> str | None:
    """`#zhaiyao .zhaiyao` / `div#zhaiyao`, then `#collapseOne .panel-body`.

    Never falls back to meta[name=description] (those sites truncate it to ~33 chars).
    """
    outer = element_inner_html(
        document, "div", lambda tag: tag_has_attr(tag, "id", "zhaiyao")
    )
    if outer:
        inner = element_inner_html(
            outer, "div", lambda tag: tag_has_attr(tag, "class", "zhaiyao", exact=False)
        )
        abstract = clean_abstract_text(html_to_text(inner if inner else outer))
        if abstract:
            return abstract
    collapse = element_inner_html(
        document, "div", lambda tag: tag_has_attr(tag, "id", "collapseOne")
    )
    if collapse:
        body = element_inner_html(
            collapse, "div", lambda tag: tag_has_attr(tag, "class", "panel-body", exact=False)
        )
        abstract = clean_abstract_text(html_to_text(body if body else collapse))
        if abstract:
            return abstract
    legacy = re.search(
        r'<td\b[^>]*class\s*=\s*["\'][^"\']*J_zhaiyao[^"\']*["\'][^>]*>\s*'
        r"<b>\s*摘\s*要\s*</b>(.*?)</td>",
        document, re.I | re.S,
    )
    if legacy:
        abstract = clean_abstract_text(html_to_text(legacy.group(1)))
        if abstract:
            return abstract
    return None


def fetch_detail_page(opener, journal: Journal, url: str, timeout: int = 25) -> str:
    request = Request(
        url,
        headers={**HEADERS, "Referer": current_issue_url(journal)},
    )
    with opener.open(request, timeout=timeout) as response:
        return decode_response(response)


def enrich_abstracts(opener, journal: Journal, items: list[dict], limit: int,
                     warnings: list, timeout: int = 25) -> int:
    """Fill empty abstracts from detail pages; existing abstracts are never replaced."""
    if limit <= 0:
        return 0
    targets = [item for item in items if not (item.get("abstract") or "").strip()][:limit]
    enriched = 0
    for index, item in enumerate(targets):
        if index:
            time.sleep(random.uniform(1.5, 2.0))
        try:
            document = fetch_detail_page(opener, journal, item["url"], timeout)
        except Exception as exc:
            warnings.append({
                "code": "ABSTRACT_ENRICH_FAILED",
                "message": f"{journal.name} {item['external_id']} 详情页请求失败：{type(exc).__name__}: {exc}",
            })
            continue
        abstract = extract_detail_abstract(document)
        if not abstract:
            warnings.append({
                "code": "ABSTRACT_ENRICH_EMPTY",
                "message": f"{journal.name} {item['external_id']} 详情页未找到可用摘要",
            })
            continue
        item["abstract"] = abstract
        enriched += 1
    return enriched


def abstract_parameters(parameters: dict):
    enrich_abstract = parameters.get("enrich_abstract", True)
    if not isinstance(enrich_abstract, bool):
        enrich_abstract = str(enrich_abstract).strip().lower() not in {"false", "0", "no", "off"}
    try:
        enrich_limit = int(parameters.get("abstract_enrich_limit", 5))
    except (TypeError, ValueError):
        raise ValueError("abstract_enrich_limit must be an integer between 0 and 10")
    return enrich_abstract, max(0, min(10, enrich_limit))


def year_bounds(request_data: dict):
    time_range = request_data.get("time_range") or {}
    values = []
    for key in ("from", "to"):
        value = time_range.get(key)
        match = re.match(r"(19\d{2}|20\d{2})", value or "")
        values.append(int(match.group(1)) if match else None)
    return values[0], values[1]


def write_output(output: Path, execution_id: str, items: list[dict], status: str, warnings: list, error=None):
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


def collect(request_data: dict):
    parameters = request_data.get("parameters") or {}
    collect_mode = parameters.get("collect_mode", "keywords")
    if collect_mode not in {"keywords", "latest_issue"}:
        raise ValueError(f"unsupported collect_mode: {collect_mode}")
    selected = parameters.get("journal_keys", DEFAULT_JOURNAL_KEYS)
    if not selected:
        raise ValueError("journal_keys cannot be empty")
    max_pages = int(parameters.get("max_pages_per_journal", 20))
    delay = int(parameters.get("request_delay_ms", 300)) / 1000
    enrich_abstract, enrich_limit = abstract_parameters(parameters)
    limit = int(request_data["limit"])
    deadline = datetime.fromisoformat(request_data["deadline_at"].replace("Z", "+00:00"))
    opener = build_opener()
    selected_journals = list(dict.fromkeys(JOURNALS[key] for key in selected if key in JOURNALS))
    unknown_journals = [key for key in selected if key not in JOURNALS]
    records, warnings, seen = [], [], set()
    for key in unknown_journals:
        warnings.append({"code": "UNKNOWN_JOURNAL", "message": f"忽略未知期刊：{key}"})
    successful_journals = 0

    journal_count = len(selected_journals)
    if collect_mode == "latest_issue":
        for journal_index, journal in enumerate(selected_journals):
            journal_limit = limit // journal_count + int(journal_index < limit % journal_count)
            if journal_limit == 0:
                break
            if datetime.now(timezone.utc) >= deadline:
                warnings.append({"code": "DEADLINE_REACHED", "message": "到达任务截止时间，已返回当前结果"})
                break
            try:
                if journal.key == STAE_KEY or journal.api_mode == "stae":
                    page_items = fetch_stae_current(opener, journal, warnings=warnings)
                else:
                    page_items = fetch_latest_issue(
                        opener, journal, max_pages, deadline, delay, warnings
                    )
            except Exception as exc:
                warnings.append({
                    "code": "JOURNAL_REQUEST_FAILED",
                    "message": f"{journal.name} 当期目次请求失败：{type(exc).__name__}: {exc}",
                })
                continue
            successful_journals += 1
            journal_items = []
            for item in page_items:
                identity = (item["journal_key"], item["external_id"])
                if identity in seen:
                    continue
                seen.add(identity)
                journal_items.append(item)
                if len(records) + len(journal_items) >= limit or len(journal_items) >= journal_limit:
                    break
            if journal_items and enrich_abstract and enrich_limit:
                if datetime.now(timezone.utc) < deadline:
                    try:
                        enrich_abstracts(opener, journal, journal_items, enrich_limit, warnings)
                    except Exception as exc:
                        warnings.append({
                            "code": "ABSTRACT_ENRICH_FAILED",
                            "message": f"{journal.name} 摘要补采异常：{type(exc).__name__}: {exc}",
                        })
            records.extend(journal_items)
            if delay:
                time.sleep(delay)
        return records, warnings, successful_journals

    terms = [safe_term(request_data["query"])]
    terms.extend(safe_term(value) for value in request_data.get("aliases", []))
    terms = list(dict.fromkeys(term for term in terms if term))
    from_year, to_year = year_bounds(request_data)

    for journal_index, journal in enumerate(selected_journals):
        journal_limit = limit // journal_count + int(journal_index < limit % journal_count)
        if journal_limit == 0:
            continue
        journal_start_count = len(records)
        journal_succeeded = False
        for term in terms:
            for page in range(1, max_pages + 1):
                if datetime.now(timezone.utc) >= deadline:
                    warnings.append({"code": "DEADLINE_REACHED", "message": "到达任务截止时间，已返回当前结果"})
                    return records, warnings, successful_journals
                try:
                    document = post_search(opener, journal, term, page)
                    page_items = parse_search_result(document, journal)
                    journal_succeeded = True
                except Exception as exc:
                    warnings.append({
                        "code": "JOURNAL_REQUEST_FAILED",
                        "message": f"{journal.name} 第 {page} 页请求失败：{type(exc).__name__}: {exc}",
                    })
                    break
                added = 0
                for item in page_items:
                    if from_year and item["year"] and item["year"] < from_year:
                        continue
                    if to_year and item["year"] and item["year"] > to_year:
                        continue
                    identity = (item["journal_key"], item["external_id"])
                    if identity in seen:
                        continue
                    seen.add(identity)
                    records.append(item)
                    added += 1
                    if len(records) - journal_start_count >= journal_limit:
                        break
                if len(records) - journal_start_count >= journal_limit:
                    break
                if page_items and added == 0 and page > 1:
                    warnings.append({
                        "code": "PAGINATION_STALLED",
                        "message": f"{journal.name} 第 {page} 页未返回新的去重文章",
                    })
                if not page_items or added == 0:
                    break
                if delay:
                    time.sleep(delay)
            if len(records) - journal_start_count >= journal_limit:
                break
        successful_journals += int(journal_succeeded)
    return records, warnings, successful_journals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request_data = json.loads(Path(args.request).read_text(encoding="utf-8"))
    output = Path(args.output)
    try:
        items, warnings, successes = collect(request_data)
        if successes == 0:
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
