from __future__ import annotations

import argparse
import html
import json
import re
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


USER_AGENT = "Mozilla/5.0 (compatible; JournalMetadataCollector/1.0)"
MAX_RESPONSE = 3_000_000
MAX_ISSUE_PAGES = 20
ABSTRACT_MIN_LENGTH = 40
ABSTRACT_MAX_LENGTH = 5000
ABSTRACT_PLACEHOLDERS = {"无", "暂无", "暂无摘要", "无摘要", "没有摘要", "摘要", "abstract", "n/a", "na", "none", "null", "undefined", "-"}
ABSTRACT_PREFIX = re.compile(
    r"^\s*(?:[［\[【]\s*(?:中文摘要|摘\s*要|Abstract)\s*[］\]】]|(?:中文摘要|摘\s*要|Abstract)\s*[:：])\s*", re.I
)
ABSTRACT_TAGS = (
    re.compile(r'<span[^>]*id=["\']Abstract["\'][^>]*>(.*?)</span>', re.I | re.S),
    re.compile(r'<(?:p|div|span)[^>]*id=["\'](?:CnAbstractValue|AbstractValue)["\'][^>]*>(.*?)</(?:p|div|span)>', re.I | re.S),
    re.compile(r'<div[^>]*class=["\'][^"\']*abstract_body[^"\']*["\'][^>]*>(.*?)</div>', re.I | re.S),
)
ABSTRACT_LABEL = re.compile(r'<span[^>]*id=["\']AbstractLabel["\'][^>]*>.*?</span>', re.I | re.S)
META_DESCRIPTION = re.compile(r'<meta\b[^>]*(?:name|property)=["\']description["\'][^>]*>', re.I)
META_CONTENT = re.compile(r'content=["\']([^"\']*)["\']', re.I)
ABSTRACT_META_START = re.compile(r'^\s*(?:[［\[【]\s*(?:中文摘要|摘\s*要)\s*[］\]】]|(?:中文摘要|摘\s*要)\s*[:：]|【目的】|【摘要】)', re.I)
EN_ABSTRACT_START = re.compile(r'(?:[［\[【]\s*Abstract\s*[］\]】]|Abstract\s*[:：])', re.I)
NOISE_TITLES = re.compile(
    r"^(?:(?:本|当|上|下|总)?期?)?(?:封面|封底|封[一二三四1-4](?:\s*[/／、,，]\s*封?[一二三四1-4])?|目[录次]|编委会|编辑委员会|版权页)$"
)
NOISE_WORDS = re.compile(r"(?:目录|目次|封面|封底|封[一二三四1-4]|版权页)")
ISSUE_MARKER = re.compile(r"(?:第\s*[0-9一二三四五六七八九十百]+\s*期|总第\s*\d+\s*期|Vol\.?\s*\d+|No\.?\s*\d+|Z\s*\d+)", re.I)
ISSUE_ONLY = re.compile(r"^(?:.{0,30})?(?:(?:19|20)\d{2}\s*年\s*)?第\s*[0-9]+\s*期$")
ISSUE_PAGE_PATH = re.compile(r"/article/issue/(\d{4}_\d+)(?:/(\d+))?/?$", re.I)
ISSUE_BLOCK_START = re.compile(
    r"<li\b[^>]*class=[\"'][^\"']*article[_-](?:line|list)[^\"']*[\"']"
    r"|<div\b[^>]*class=[\"'][^\"']*article[_-]list[^\"']*[\"'][^>]*\bid=[\"']",
    re.I,
)
TITLE_ANCHOR = re.compile(
    r"<(?:div|p|h[1-6]|span)\b[^>]*class=[\"'][^\"']*article[_-](?:list[_-])?title[^\"']*[\"'][^>]*>"
    r".*?<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.I | re.S,
)
PAGER_ANCHOR = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
PAGER_PARAMS = ("page", "pageNum", "pageNo", "page_no", "paged", "p")
LEGACY_PAGE_COUNT = re.compile(r"<span\b[^>]*id=['\"]PageCount['\"][^>]*>\s*(\d+)\s*</span>", re.I)
PAGE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
ISSUE_BROWSER_JSON = re.compile(r"strAllIssueJson\s*=\s*(\"(?:[^\"\\]|\\.)*\")\s*;", re.S)


def read_response(opener, request, timeout):
    with opener.open(request, timeout=timeout) as response:
        content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        charset = response.headers.get_content_charset()
        if not charset:
            match = re.search(rb"charset\s*=\s*['\"]?([A-Za-z0-9_-]+)", content[:4000], re.I)
            charset = match.group(1).decode("ascii") if match else "utf-8"
        try:
            text = content.decode(charset, errors="replace")
        except LookupError:
            text = content.decode("utf-8", errors="replace")
        return text, response.geturl()


def discover_search(opener, journal, query, timeout):
    base = journal["url"].rstrip("/")
    publisher = journal.get("publisher")
    if not publisher:
        page, redirected = read_response(opener, Request(base, headers={"User-Agent": USER_AGENT}), timeout)
        match = re.search(r"(?i)href\s*=\s*['\"]/?([\w-]+)/home(?:[?'\"])", page)
        if not match:
            raise ValueError("UNSUPPORTED_TEMPLATE: no Qinyun /publisher/home link")
        publisher = match.group(1)
        base = f"{urlsplit(redirected).scheme}://{urlsplit(redirected).netloc}"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", publisher):
        raise ValueError("invalid Qinyun publisher path")
    search_url = f"{base}/{publisher}/article/search?key={quote(query)}"
    page, _ = read_response(opener, Request(search_url, headers={"User-Agent": USER_AGENT}), timeout)
    if "/ajax/search" not in page:
        raise ValueError("UNSUPPORTED_TEMPLATE: no Qinyun AJAX search marker")
    hidden = re.search(r"<input\b(?=[^>]*\bname=['\"]CsrfCheckCode['\"])[^>]*>", page, re.I)
    csrf = re.search(r"\bvalue=['\"]([^'\"]*)['\"]", hidden.group(0), re.I) if hidden else None
    if not csrf or not csrf.group(1):
        raise ValueError("UNSUPPORTED_TEMPLATE: missing CsrfCheckCode")
    return base, publisher, html.unescape(csrf.group(1))


def search_page(opener, base, publisher, csrf, query, page, timeout):
    payload = {
        "from_year": "", "to_year": "", "search_type": "search", "source_type": "meta",
        "field": "", "key": query, "additional_year": "", "additional_author": "",
        "additional_keyword": "", "page": str(page), "page_size": "10", "CsrfCheckCode": csrf,
    }
    request = Request(
        f"{base}/{publisher}/ajax/search", data=urlencode(payload).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Referer": f"{base}/{publisher}/home", "X-Requested-With": "XMLHttpRequest"},
    )
    raw, _ = read_response(opener, request, timeout)
    data = json.loads(raw)
    if isinstance(data, dict) and data.get("rows") is None and (
        data.get("records") in (0, "0") or data.get("total") in (0, "0")
    ):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError("UNSUPPORTED_TEMPLATE: Qinyun response lacks rows")
    return data["rows"]


def normalize(record, journal, base, publisher):
    if not isinstance(record, dict):
        return None
    title = html.unescape(re.sub(r"<[^>]+>", "", str(record.get("title") or ""))).strip()
    external_id = str(record.get("file_no") or "").strip()
    if not title or not external_id or is_noise_title(title):
        return None
    doi = str(record.get("doi") or "").strip()
    raw_url = str(record.get("abstract_url") or "").strip()
    article_url = urljoin(base + "/", raw_url.lstrip("/")) if raw_url else f"{base}/{publisher}/article/abstract/{quote(external_id)}"
    year_raw = str(record.get("year_id") or "")[:4]
    author = html.unescape(re.sub(r"<[^>]+>", "", str(record.get("author_name") or record.get("display_author_name") or ""))).strip()
    abstract = clean_abstract(record.get("abstract"))
    return {
        "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
        "journal_url": journal["url"], "external_id": external_id[:128],
        "title": title[:1000], "url": article_url, "authors": author or None,
        "abstract": abstract, "doi": doi[:255] or None,
        "year": int(year_raw) if year_raw.isdigit() else None,
    }


def hidden_fields(page):
    result = {}
    for tag in re.findall(r"<input\b[^>]*>", page, re.I):
        if not re.search(r"\btype=['\"]hidden['\"]", tag, re.I):
            continue
        name = re.search(r"\bname=['\"]([^'\"]+)['\"]", tag, re.I)
        value = re.search(r"\bvalue=['\"]([^'\"]*)['\"]", tag, re.I)
        if name:
            result[html.unescape(name.group(1))] = html.unescape(value.group(1)) if value else ""
    return result


def discover_old_search(opener, journal, timeout):
    base = journal["url"].rstrip("/")
    home, redirected = read_response(opener, Request(base, headers={"User-Agent": USER_AGENT}), timeout)
    match = re.search(r"(?:href|action)\s*=\s*['\"]([^'\"]*reader/key_query\.aspx[^'\"]*)['\"]", home, re.I)
    candidates = [urljoin(redirected, html.unescape(match.group(1)))] if match else []
    candidates.append(f"{urlsplit(redirected).scheme}://{urlsplit(redirected).netloc}/ch/reader/key_query.aspx")
    for search_url in dict.fromkeys(candidates):
        try:
            page, actual_url = read_response(opener, Request(search_url, headers={"User-Agent": USER_AGENT}), timeout)
        except Exception:
            continue
        if "__VIEWSTATE" in hidden_fields(page) and "key_query.aspx" in actual_url.lower():
            return actual_url, page
    raise ValueError("UNSUPPORTED_TEMPLATE: no ASP.NET key_query form")


def old_form_payload(page, query, next_page=False):
    payload = hidden_fields(page)
    if "__VIEWSTATE" not in payload:
        raise ValueError("UNSUPPORTED_TEMPLATE: missing ASP.NET viewstate")
    names = {match.group(1) for match in re.finditer(r"\bname=['\"]([^'\"]+)['\"]", page, re.I)}
    key_name = next((name for name in ("Key", "key", "keyword") if name in names), None)
    if not key_name:
        raise ValueError("UNSUPPORTED_TEMPLATE: unknown ASP.NET query field")
    payload[key_name] = query
    if "KeyList" in names:
        payload["KeyList"] = "title"
    payload["__EVENTTARGET"] = "next" if next_page else ""
    payload["__EVENTARGUMENT"] = ""
    if not next_page:
        button = next((name for name in ("Query", "Submit", "submit") if name in names), None)
        if not button:
            raise ValueError("UNSUPPORTED_TEMPLATE: unknown ASP.NET submit button")
        payload[button] = "检 索"
    return payload


def old_search_page(opener, search_url, page, query, timeout, next_page=False):
    payload = old_form_payload(page, query, next_page)
    request = Request(search_url, data=urlencode(payload).encode("utf-8"), headers={
        "User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": search_url,
    })
    result, actual_url = read_response(opener, request, timeout)
    if "key_query.aspx" not in actual_url.lower() and "view_abstract.aspx" not in result.lower():
        raise ValueError("UNSUPPORTED_TEMPLATE: old search did not return a result page")
    return result


def old_page_items(page, search_url, journal):
    seen = set()
    items = []
    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", page, re.I | re.S):
        match = re.search(r"<a\b[^>]*href=['\"]([^'\"]*view_abstract\.aspx\?[^'\"]*)['\"][^>]*>(.*?)</a>", row, re.I | re.S)
        if not match:
            continue
        link = urljoin(search_url, html.unescape(match.group(1)))
        file_no = re.search(r"[?&]file_no=([^&]+)", link, re.I)
        title = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", match.group(2))).split())
        if not file_no or not title or file_no.group(1) in seen or is_noise_title(title):
            continue
        seen.add(file_no.group(1))
        cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", cell)).split()) for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.I | re.S)]
        authors = next((cell for cell in cells if cell and cell != title and not re.search(r"\d{4}.*\d+", cell)), None)
        year = re.search(r"\b(19|20)\d{2}\b", " ".join(cells))
        items.append({
            "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
            "journal_url": journal["url"], "external_id": file_no.group(1)[:128],
            "title": title[:1000], "url": link, "authors": authors,
            "abstract": None, "doi": None, "year": int(year.group(0)) if year else None,
        })
    return items


def enrich_old_detail(opener, item, timeout):
    try:
        detail, _ = read_response(opener, Request(item["url"], headers={"User-Agent": USER_AGENT}), timeout)
    except Exception:
        return item
    item["abstract"] = extract_abstract(detail) or item.get("abstract")
    doi = re.search(r"<span\b[^>]*id=['\"]DOI['\"][^>]*>(.*?)</span>", detail, re.I | re.S)
    if doi:
        item["doi"] = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", doi.group(1))).split())[:255] or None
    return item


def clean_text(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())


def page_base(page, fallback):
    match = re.search(r'<base\b[^>]*href=["\']([^"\']+)["\']', page, re.I)
    if not match:
        return fallback
    try:
        return urljoin(fallback, html.unescape(match.group(1)))
    except ValueError:
        return fallback


def is_noise_title(title):
    title = " ".join(str(title or "").split())
    if not title:
        return True
    if NOISE_TITLES.match(title):
        return True
    if re.search(r"(?:编委会|编辑委员会|投稿须知|征稿启事|稿约|版权页)", title):
        return True
    if ISSUE_ONLY.match(title):
        return True
    return bool(NOISE_WORDS.search(title) and ISSUE_MARKER.search(title))


def clean_abstract(value):
    text = clean_text(value)
    if not text:
        return None
    text = ABSTRACT_PREFIX.sub("", text).strip()
    if len(text) < ABSTRACT_MIN_LENGTH:
        return None
    lowered = text.strip(" .。:：;；").lower()
    if lowered in ABSTRACT_PLACEHOLDERS or lowered.startswith(("暂无摘要", "无摘要", "暂无内容", "没有摘要")):
        return None
    return text[:ABSTRACT_MAX_LENGTH]


def label_abstract(page):
    match = ABSTRACT_LABEL.search(page)
    if not match:
        return None
    tail = page[match.end():match.end() + 8000]
    close = tail.find("</td>")
    if close >= 0:
        tail = tail[close + len("</td>"):]
    cell = re.search(r'<td\b[^>]*>(.*?)</td>', tail, re.I | re.S)
    if not cell or re.search(r'id=["\'](?:KeyWord|EnKeyWord)["\']', cell.group(1), re.I):
        return None
    if re.match(r"^\s*(?:关键词|关键字|Key\s*words?|DOI)\s*[:：]", clean_text(cell.group(1)), re.I):
        return None
    return clean_abstract(cell.group(1))


def meta_abstract(page):
    for meta in META_DESCRIPTION.finditer(page):
        content = META_CONTENT.search(meta.group(0))
        if not content:
            continue
        text = clean_text(content.group(1))
        if not text or not ABSTRACT_META_START.match(text):
            continue
        cut = EN_ABSTRACT_START.search(text, 40)
        if cut:
            text = text[:cut.start()]
        abstract = clean_abstract(text)
        if abstract:
            return abstract
    return None


def extract_abstract(page):
    for pattern in ABSTRACT_TAGS:
        for match in pattern.finditer(page):
            abstract = clean_abstract(match.group(1))
            if abstract:
                return abstract
    return label_abstract(page) or meta_abstract(page)


def enrich_abstract(opener, item, timeout):
    if item.get("abstract") or not item.get("url"):
        return item
    try:
        page, _ = read_response(opener, Request(item["url"], headers={"User-Agent": USER_AGENT}), timeout)
        abstract = extract_abstract(page)
        if abstract:
            item["abstract"] = abstract
    except Exception:
        pass
    return item


def enrich_abstracts(opener, rows, timeout, limit):
    if limit <= 0:
        return rows
    attempts = 0
    for item in rows:
        if item.get("abstract") or not item.get("url"):
            continue
        if attempts >= limit:
            break
        enrich_abstract(opener, item, timeout)
        attempts += 1
    return rows


def split_issue_blocks(page):
    """Split an issue page into per-article blocks, keeping the opening tag."""
    starts = [match.start() for match in ISSUE_BLOCK_START.finditer(page)]
    return [page[start:end] for start, end in zip(starts, starts[1:] + [len(page)])]


def issue_signature(url):
    """Identify the issue a URL belongs to (new-style /article/issue/Y_N or legacy year_id/quarter_id)."""
    parts = urlsplit(url)
    match = ISSUE_PAGE_PATH.search(parts.path)
    if match:
        return ("issue", match.group(1))
    query = parse_qs(parts.query, keep_blank_values=True)
    if query.get("year_id") and query.get("quarter_id"):
        return ("legacy", query["year_id"][0], query["quarter_id"][0])
    return None


def pager_link_target(base_url, target_url):
    """Return the page number when target_url is a same-issue pagination link, else None.

    Only links that keep the same host and issue (same /article/issue/Y_N prefix or the same
    year_id/quarter_id) and change nothing but a page parameter are accepted.
    """
    base, target = urlsplit(base_url), urlsplit(target_url)
    if base.netloc.lower() != target.netloc.lower():
        return None
    signature = issue_signature(base_url)
    if signature is None:
        return None
    if signature[0] == "issue":
        target_match = ISSUE_PAGE_PATH.search(target.path)
        if not target_match or target_match.group(1) != signature[1]:
            return None
        base_path = base.path.rstrip("/")
        target_path = target.path.rstrip("/")
        if target_path != base_path and not re.fullmatch(re.escape(base_path) + r"/\d+", target_path):
            return None
    else:
        if target.path.rstrip("/") != base.path.rstrip("/"):
            return None
        query = parse_qs(target.query, keep_blank_values=True)
        if query.get("year_id", [""])[0] != signature[1]:
            return None
        if query.get("quarter_id", [""])[0] != signature[2]:
            return None
    base_query = dict(parse_qsl(base.query, keep_blank_values=True))
    target_query = dict(parse_qsl(target.query, keep_blank_values=True))
    for name in PAGER_PARAMS:
        base_query.pop(name, None)
        target_query.pop(name, None)
    if base_query != target_query:
        return None
    target_values = parse_qs(target.query, keep_blank_values=True)
    for name in PAGER_PARAMS:
        values = target_values.get(name)
        if not values:
            continue
        if not values[0].isdigit():
            return None
        number = int(values[0])
        return number if 1 < number <= MAX_ISSUE_PAGES else None
    target_match = ISSUE_PAGE_PATH.search(target.path)
    if target_match and target_match.group(2):
        number = int(target_match.group(2))
        return number if 1 < number <= MAX_ISSUE_PAGES else None
    return None


def discover_issue_pages(page, page_url, max_pages=MAX_ISSUE_PAGES):
    """Return [(page_number, url)] only when the page links to the same issue's next pages."""
    found = {}
    for match in PAGER_ANCHOR.finditer(page):
        href = html.unescape(match.group(1)).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        target = urljoin(page_url, href).split("#", 1)[0]
        number = pager_link_target(page_url, target)
        if number is None or number > max_pages:
            continue
        found.setdefault(number, target)
    page_count = LEGACY_PAGE_COUNT.search(page)
    if page_count:
        cap = int(page_count.group(1))
        if 1 < cap <= max_pages:
            found = {number: url for number, url in found.items() if number <= cap}
    return sorted(found.items())


def issue_page_marker(page):
    match = PAGE_TITLE.search(page)
    if not match:
        return None
    marker = ISSUE_MARKER.search(clean_text(match.group(1)))
    return marker.group(0).replace(" ", "").lower() if marker else None


def issue_drop_report(page, items):
    """List FileNO entries that were not emitted and are not cover/contents noise."""
    parsed = {item["external_id"] for item in items}
    lost, seen = [], set()
    for block in split_issue_blocks(page):
        match = re.search(r"id=['\"]FileNO([^'\"]+)", block, re.I)
        if not match:
            continue
        file_no = match.group(1)
        if file_no in parsed or file_no in seen:
            continue
        seen.add(file_no)
        title_match = TITLE_ANCHOR.search(block)
        title = clean_text(title_match.group(2)) if title_match else ""
        if title and is_noise_title(title):
            continue
        lost.append({"external_id": file_no, "title": title[:200]})
    return lost


def audit_issue_page(page, items, journal, warnings):
    if warnings is None:
        return
    lost = issue_drop_report(page, items)
    if lost:
        warnings.append(f"{journal['name']}: 当期 {len(lost)} 条未解析（如 {lost[0]['external_id']}）")


def extend_issue_pages(opener, journal, issue_url, first_page, first_items, timeout, mode="new", warnings=None):
    """Follow same-issue pagination only when the page exposes real page links (hard cap 20)."""
    audit_issue_page(first_page, first_items, journal, warnings)
    candidates = discover_issue_pages(first_page, issue_url)
    if not candidates:
        return first_items
    marker = issue_page_marker(first_page)
    items = list(first_items)
    seen = {item["external_id"] for item in items}
    followed, stop_reason = 0, "max_pages"
    for _, target in candidates:
        if followed >= MAX_ISSUE_PAGES - 1:
            break
        try:
            page, _ = read_response(opener, Request(target, headers={"User-Agent": USER_AGENT}), timeout)
        except Exception as exc:
            stop_reason = f"fetch_error:{type(exc).__name__}"
            break
        page_marker = issue_page_marker(page)
        if marker and page_marker and page_marker != marker:
            stop_reason = "issue_changed"
            break
        if mode == "old":
            page_items = old_page_items(page, target, journal)
        else:
            page_items = parse_new_issue_page(page, target, journal)
            if not page_items or any("{{@" in item.get("title", "") for item in page_items):
                embedded = embedded_issue_items(page, target, journal)
                if embedded:
                    page_items = embedded
        audit_issue_page(page, page_items, journal, warnings)
        fresh = [item for item in page_items if item["external_id"] not in seen]
        if not fresh:
            stop_reason = "no_new_items"
            break
        for item in fresh:
            seen.add(item["external_id"])
            items.append(item)
        followed += 1
    else:
        stop_reason = "exhausted"
    if warnings is not None and followed:
        warnings.append(f"{journal['name']}: 当期分页跟随 {followed} 页（停止：{stop_reason}）")
    return items


def parse_new_issue_page(page, issue_url, journal):
    base_url = page_base(page, journal["url"].rstrip("/") + "/")
    items, seen = [], set()
    for block in split_issue_blocks(page):
        if "</li>" in block:
            block = block.split("</li>", 1)[0]
        title_link = TITLE_ANCHOR.search(block)
        if not title_link:
            continue
        title = clean_text(title_link.group(2))
        href = html.unescape(title_link.group(1))
        file_no = re.search(r"id=['\"]FileNO([^'\"]+)", block, re.I) or re.search(r"article/abstract/([^/'\"?]+)", href, re.I)
        external_id = file_no.group(1) if file_no else href.rstrip("/").split("/")[-1]
        if not title or is_noise_title(title) or not external_id or external_id in seen:
            continue
        seen.add(external_id)
        authors_match = re.search(r'<(?:p|div)[^>]*class=["\'][^"\']*article[_-](?:list[_-])?author[^"\']*["\'][^>]*>(.*?)</(?:p|div)>', block, re.I | re.S)
        position_match = re.search(r'<(?:p|div)[^>]*class=["\'][^"\']*article[_-](?:list[_-])?(?:position|time)[^"\']*["\'][^>]*>(.*?)</(?:p|div)>', block, re.I | re.S)
        abstract_match = re.search(r'<(?:div|span)[^>]*class=["\'][^"\']*(?:abstract_body|article[_-]list[_-]abstract_content)[^"\']*["\'][^>]*>(.*?)</(?:div|span)>', block, re.I | re.S)
        position = clean_text(position_match.group(1)) if position_match else ""
        year_match = re.search(r"(19\d{2}|20\d{2})", position)
        doi_match = re.search(r"10\.\d{4,9}/[^\s\"'<>]+", position + " " + block, re.I)
        items.append({
            "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
            "journal_url": journal["url"], "external_id": external_id[:128],
            "title": title[:1000], "url": urljoin(base_url, href),
            "authors": clean_text(authors_match.group(1)) or None if authors_match else None,
            "abstract": clean_abstract(abstract_match.group(1)) if abstract_match else None,
            "doi": doi_match.group(0).rstrip(".,;，；")[:255] if doi_match else None,
            "year": int(year_match.group(0)) if year_match else None,
        })
    return items


def embedded_issue_items(page, issue_url, journal):
    match = re.search(r"strArticleListJson\s*=\s*`(.*?)`\s*;", page, re.S)
    if not match:
        return []
    base_url = page_base(page, journal["url"].rstrip("/") + "/")
    raw = match.group(1).replace("\\u0022", '"').replace("\\u0027", "'").replace("\\u005C", "\\")
    try:
        records = json.loads(raw)
    except Exception:
        return []
    items, seen = [], set()
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        title = clean_text(record.get("title"))
        file_no = str(record.get("file_no") or "").strip()
        if not title or not file_no or file_no in seen or is_noise_title(title):
            continue
        seen.add(file_no)
        raw_url = str(record.get("abstract_url") or "").strip()
        authors = record.get("author_array") or []
        if isinstance(authors, list):
            authors = "、".join(clean_text(value) for value in authors if clean_text(value))
        else:
            authors = clean_text(authors)
        position = clean_text(record.get("position"))
        year_match = re.search(r"(19\d{2}|20\d{2})", position)
        items.append({
            "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
            "journal_url": journal["url"], "external_id": file_no[:128],
            "title": title[:1000], "url": urljoin(base_url, raw_url.lstrip("/")) if raw_url else journal["url"],
            "authors": authors or None, "abstract": clean_abstract(record.get("abstract")),
            "doi": clean_text(record.get("doi")) or None,
            "year": int(year_match.group(0)) if year_match else None,
        })
    return items


def issue_browser_latest(page, page_url):
    """Resolve the newest /article/issue/Y_N URL from a Qinyun issue browser page."""
    match = ISSUE_BROWSER_JSON.search(page)
    if not match:
        return None
    try:
        payload = json.loads(json.loads(match.group(1)))
    except (TypeError, ValueError):
        return None
    years = payload.get("years") if isinstance(payload, dict) else None
    if not isinstance(years, list):
        return None

    def order(value):
        number = re.match(r"\d+", str(value or ""))
        return int(number.group(0)) if number else -1

    for year in sorted(
        (item for item in years if isinstance(item, dict)),
        key=lambda item: order(item.get("year_id")), reverse=True,
    ):
        issues = [
            item for item in year.get("issues") or []
            if isinstance(item, dict) and str(item.get("issue_url") or "").strip()
        ]
        if not issues:
            continue
        issue = max(issues, key=lambda item: order(item.get("issue_id")))
        target = html.unescape(str(issue["issue_url"])).strip()
        if target:
            return urljoin(page_base(page, page_url), target)
    return None


def current_issue_items(opener, journal, timeout, warnings=None):
    explicit = journal.get("current_url")
    if explicit:
        page, _ = read_response(opener, Request(explicit, headers={"User-Agent": USER_AGENT}), timeout)
        mode = "old" if "issue_list.aspx" in explicit.lower() else "new"
        items = parse_new_issue_page(page, explicit, journal)
        if not items or any("{{@" in item.get("title", "") for item in items):
            items = embedded_issue_items(page, explicit, journal)
        if not items and mode == "old":
            items = old_page_items(page, explicit, journal)
        if items:
            return extend_issue_pages(opener, journal, explicit, page, items, timeout, mode, warnings)
        browser_issue = issue_browser_latest(page, explicit)
        if browser_issue and browser_issue != explicit:
            issue_page, _ = read_response(opener, Request(browser_issue, headers={"User-Agent": USER_AGENT}), timeout)
            items = parse_new_issue_page(issue_page, browser_issue, journal)
            if not items:
                items = embedded_issue_items(issue_page, browser_issue, journal)
            if items:
                return extend_issue_pages(opener, journal, browser_issue, issue_page, items, timeout, "new", warnings)
        redirect = re.search(r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", page, re.I)
        if redirect:
            target = html.unescape(redirect.group(1))
            if not target.startswith(("http://", "https://", "/")):
                target = "/" + target
            issue_url = urljoin(journal["url"], target)
            issue_page, _ = read_response(opener, Request(issue_url, headers={"User-Agent": USER_AGENT}), timeout)
            items = parse_new_issue_page(issue_page, issue_url, journal)
            if not items:
                items = embedded_issue_items(issue_page, issue_url, journal)
            if items:
                return extend_issue_pages(opener, journal, issue_url, issue_page, items, timeout, "new", warnings)
    base = journal["url"].rstrip("/")
    home, final_url = read_response(opener, Request(base, headers={"User-Agent": USER_AGENT}), timeout)
    new_links = {}
    for href, year, issue in re.findall(
        r'href=["\']([^"\']*/article/issue/(\d{4})_(\d+)[^"\']*)["\']', home, re.I
    ):
        new_links[(int(year), int(issue))] = urljoin(final_url, html.unescape(href))
    if new_links:
        issue_url = new_links[max(new_links)]
        page, _ = read_response(opener, Request(issue_url, headers={"User-Agent": USER_AGENT}), timeout)
        items = parse_new_issue_page(page, issue_url, journal)
        if items:
            return extend_issue_pages(opener, journal, issue_url, page, items, timeout, "new", warnings)

    old_links = {}
    for href, year, quarter in re.findall(
        r'href=["\']([^"\']*issue_list\.aspx\?[^"\']*year_id=(\d{4})[^"\']*quarter_id=(\d+)[^"\']*)["\']',
        home, re.I,
    ):
        old_links[(int(year), int(quarter))] = urljoin(final_url, html.unescape(href))
    if not old_links:
        for href in re.findall(r'href=["\']([^"\']*issue_browser\.aspx[^"\']*)["\']', home, re.I):
            browser_url = urljoin(final_url, html.unescape(href))
            try:
                browser, _ = read_response(opener, Request(browser_url, headers={"User-Agent": USER_AGENT}), timeout)
            except Exception:
                continue
            for link, year, quarter in re.findall(
                r'href=["\']([^"\']*issue_list\.aspx\?[^"\']*year_id=(\d{4})[^"\']*quarter_id=(\d+)[^"\']*)["\']',
                browser, re.I,
            ):
                old_links[(int(year), int(quarter))] = urljoin(browser_url, html.unescape(link))
    if old_links:
        issue_url = old_links[max(old_links)]
        page, _ = read_response(opener, Request(issue_url, headers={"User-Agent": USER_AGENT}), timeout)
        items = old_page_items(page, issue_url, journal)
        if items:
            return extend_issue_pages(opener, journal, issue_url, page, items, timeout, "old", warnings)
    raise ValueError("UNSUPPORTED_TEMPLATE: no current issue items")


def collect_old(opener, journal, query, limit, timeout):
    search_url, page = discover_old_search(opener, journal, timeout)
    seen = set()
    items = []
    for number in range(1, min(100, (limit + 19) // 20) + 1):
        result = old_search_page(opener, search_url, page, query, timeout, next_page=number > 1)
        new_items = old_page_items(result, search_url, journal)
        for item in new_items:
            if item["external_id"] not in seen:
                seen.add(item["external_id"])
                items.append(item)
                if len(items) >= limit:
                    break
        if len(items) >= limit or not new_items:
            break
        page_count = re.search(r"<span\b[^>]*id=['\"]PageCount['\"][^>]*>(\d+)</span>", result, re.I)
        if not page_count or number >= int(page_count.group(1)):
            break
        page = result
    return [enrich_old_detail(opener, item, timeout) for item in items]


def abstract_enrich_options(params):
    enabled = params.get("enrich_abstract", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"false", "0", "no", "off"}
    try:
        limit = int(params.get("abstract_enrich_limit", 5))
    except (TypeError, ValueError):
        limit = 5
    return bool(enabled), max(0, min(limit, 20))


def collect(request_data, journals):
    params = request_data.get("parameters") or {}
    mode = params.get("collect_mode", "keywords")
    if mode not in {"keywords", "latest_issue"}:
        raise ValueError(f"unsupported collect_mode: {mode}")
    keys = params.get("journal_keys", ["jos"])
    if not keys or not request_data["query"].strip():
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
                enrich_enabled, enrich_limit = abstract_enrich_options(params)
                if enrich_enabled and enrich_limit:
                    rows = enrich_abstracts(opener, rows, timeout, enrich_limit)
                for item in rows:
                    if item["external_id"] in seen:
                        continue
                    seen.add(item["external_id"])
                    items.append(item)
                    if len(seen) >= per_journal or len(items) >= limit:
                        break
                successful += 1
                continue
            try:
                base, publisher, csrf = discover_search(opener, journal, request_data["query"].strip(), timeout)
            except ValueError as exc:
                if "UNSUPPORTED_TEMPLATE" not in str(exc):
                    raise
                items.extend(collect_old(opener, journal, request_data["query"].strip(), min(per_journal, limit - len(items)), timeout))
            else:
                for page in range(1, min(100, per_journal) + 1):
                    rows = search_page(opener, base, publisher, csrf, request_data["query"].strip(), page, timeout)
                    if not rows:
                        break
                    previous_count = len(seen)
                    for record in rows:
                        item = normalize(record, journal, base, publisher)
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
