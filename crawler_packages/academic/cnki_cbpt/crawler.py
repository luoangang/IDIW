from __future__ import annotations

import argparse
import html as html_lib
import json
import random
import re
import sys
import time
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class PaperParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.paper_depth = 0
        self.paper = None
        self.capture = None
        self.author_seen = False
        self.papers = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        self.stack.append((tag, classes))
        if tag == "div" and "paperBox" in classes and self.paper is None:
            self.paper = {"title": "", "url": "", "authors": "", "abstract": "", "issue": ""}
            self.paper_depth = len(self.stack)
            self.author_seen = False
        if self.paper is None:
            return
        if tag == "a" and any(parent == "h3" for parent, _ in self.stack[:-1]):
            link = attrs.get("href") or ""
            if "/client/paper/" in link:
                self.paper["url"] = link
                self.capture = "title"
        elif tag == "span" and len(self.stack) == self.paper_depth + 1:
            self.author_seen = True
            self.capture = "authors"
        elif (tag == "p" and not classes
              and len(self.stack) == self.paper_depth + 1
              and self.paper["abstract"] == ""
              and self.author_seen):
            # On type_benqi pages the full abstract is the unclassed <p>
            # directly after the author <span> (which may be empty for
            # notices). p.highText is a truncated search-hit snippet and
            # is deliberately ignored.
            self.capture = "abstract"
        elif tag == "span" and "publish-info" in classes:
            self.capture = "issue"

    def handle_data(self, data):
        if self.paper is not None and self.capture:
            self.paper[self.capture] += data

    def handle_endtag(self, tag):
        if not self.stack:
            return
        if self.paper is not None:
            if self.capture == "title" and tag == "a":
                self.capture = None
            elif self.capture == "authors" and tag == "span":
                self.capture = None
            elif self.capture == "abstract" and tag == "p":
                self.capture = None
            elif self.capture == "issue" and tag == "span":
                self.capture = None
            if tag == "div" and len(self.stack) == self.paper_depth:
                for key in ("title", "authors", "abstract", "issue"):
                    self.paper[key] = " ".join(self.paper[key].split())
                if self.paper["title"] and self.paper["url"] and not is_noise_title(self.paper["title"]):
                    self.papers.append(self.paper)
                self.paper = None
                self.paper_depth = 0
                self.author_seen = False
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def read_page(base_url, query, page, timeout):
    api = urljoin(base_url, "/portal/journal/portal/journal/api/listContent")
    body = json.dumps({"newsId": "", "xianzaiId": "", "content": query, "pageNum": page, "pageSize": 10}).encode("utf-8")
    request = Request(api, data=body, headers={
        **HEADERS,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "text/html, */*",
    })
    with urlopen(request, timeout=timeout) as response:
        document = response.read(3_000_001)
        if len(document) > 3_000_000:
            raise ValueError("search response exceeds 3 MB")
        html = document.decode("utf-8", errors="replace")
    if "searchZone" not in html or "listContent" not in html:
        raise ValueError("site did not return a CBPT search page")
    parser = PaperParser()
    parser.feed(html)
    return parser.papers


def current_issue_url(base_url):
    return urljoin(base_url, "/portal/journal/portal/client/paper_list/type_benqi")


def fetch_html(url, timeout, opener=None):
    request = Request(url, headers=HEADERS)
    open_page = opener.open if opener is not None else urlopen
    with open_page(request, timeout=timeout) as response:
        document = response.read(3_000_001)
        if len(document) > 3_000_000:
            raise ValueError("current issue page exceeds 3 MB")
        return document.decode("utf-8", errors="replace")


def make_opener():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def is_validate_shell(page):
    return "showValidateCode.aspx" in page or "ValidateCodeZH" in page


PLACEHOLDER_ABSTRACTS = {"无", "暂无", "暂无摘要", "无摘要", "略"}
PLACEHOLDER_CHARS = set("~～-—_.。·…,，;；:： \t\r\n")
NOISE_TITLE_PREFIX = re.compile(r"^(?:欢迎订阅|欢迎投稿|本刊被|本刊已|敬告|征稿|征订|订阅|公告|启事|声明|通知|招聘|致作者|版权)")
NOISE_TITLE_SUFFIX = re.compile(r"(?:公告|启事|声明|通知|稿约|编后|召开|典型案例)$")


def is_noise_title(value):
    text = " ".join(str(value or "").split())
    if not text:
        return True
    if NOISE_TITLE_PREFIX.search(text):
        return True
    return len(text) <= 60 and bool(NOISE_TITLE_SUFFIX.search(text))


def clean_abstract(value, title=None):
    if not value:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    text = re.sub(r"^<正>\s*", "", text)
    if not text:
        return None
    if set(text) <= PLACEHOLDER_CHARS or text in PLACEHOLDER_ABSTRACTS:
        return None
    if title and text == " ".join(str(title).split()):
        return None
    return text


def extract_wk_abstract(page):
    """Return the paragraph right after <p id="digest">, or None."""
    for match in re.finditer(r'<p\b[^>]*\bid\s*=\s*["\']digest["\'][^>]*>', page, re.I):
        close = page.lower().find("</p>", match.end())
        if close == -1:
            continue
        following = re.search(r"<p\b[^>]*>(.*?)</p>", page[close + 4:], re.I | re.S)
        if not following:
            continue
        text = html_lib.unescape(re.sub(r"<[^>]+>", " ", following.group(1)))
        return " ".join(text.split())
    return None


def read_wkd_current(current_url, timeout, opener=None, warn=None):
    page = fetch_html(current_url, timeout, opener)
    if warn is not None and "paperPage_list" in page:
        warn("WebPublication 当期页包含 paperPage_list 控件，当前实现仅采集第 1 页")
    records = []
    pattern = re.compile(
        r'<li[^>]*>\s*<h3>\s*<a[^>]+href=["\']([^"\']*paperDigest\.aspx\?paperID=([^"\']+))["\'][^>]*>(.*?)</a>\s*</h3>\s*<samp>(.*?)</samp>\s*<span>(.*?)</span>',
        re.I | re.S,
    )
    for match in pattern.finditer(page):
        title = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", match.group(3))).split())
        if not title:
            continue
        article_url = urljoin(current_url, html_lib.unescape(match.group(1)))
        authors = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", match.group(4))).replace(";", ",").split())
        meta = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", match.group(5))).split())
        issue = re.search(r"(20\d{2}年\d+期)", meta)
        records.append({
            "url": article_url, "title": title,
            "authors": authors or None, "abstract": None,
            "issue": issue.group(1) if issue else None,
            "external_id": match.group(2),
        })
    if not records:
        for href, text in re.findall(
            r'<a\b[^>]*href=["\']([^"\']*paperDigest\.aspx\?paperID=[^"\']+)["\'][^>]*>(.*?)</a>',
            page, re.I | re.S,
        ):
            title = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", text)).split())
            if len(title) < 8 or is_noise_title(title) or re.search(r"(目录|封面|封底|征稿|启事|稿约|来稿须知|投稿须知)", title):
                continue
            article_url = urljoin(current_url, html_lib.unescape(href))
            paper_id = (parse_qs(urlsplit(article_url).query).get("paperID") or [""])[0]
            records.append({
                "url": article_url, "title": title,
                "authors": None, "abstract": None, "issue": None,
                "external_id": paper_id,
            })
    return records


def enrich_wk_abstracts(key, journal, items, opener, timeout, limit, warnings):
    """Fetch paperDigest.aspx for up to `limit` items using the list-page session.

    Serial requests with a 0.5-1s gap. A validate-code shell means the anonymous
    session was not accepted; record a warning, stop this journal, never bypass.
    Individual failures are non-fatal.
    """
    attempts = 0
    for item in items:
        if attempts >= limit:
            break
        if item["abstract"]:
            continue
        if attempts:
            time.sleep(random.uniform(0.5, 1.0))
        attempts += 1
        try:
            page = fetch_html(item["url"], timeout, opener)
        except Exception as exc:
            warnings.append(
                f"{key} ({journal['name']}): abstract detail failed for "
                f"{item['external_id']}: {type(exc).__name__}: {exc}")
            continue
        if is_validate_shell(page):
            warnings.append(
                f"{key} ({journal['name']}): validate code shell on abstract detail; "
                "abstract left empty and remaining details skipped")
            break
        abstract = clean_abstract(extract_wk_abstract(page), item["title"])
        if abstract:
            item["abstract"] = abstract


PAGER_HREF = re.compile(r'href=["\']([^"\']*paperPage_list\?[^"\']*)["\']', re.I)
PAGER_PAGE_NUM = re.compile(r"[?&](?:amp;)?pageNum=(\d+)", re.I)
PAGER_IDENTITY_PARAMS = ("yearId", "issueId")
DEFAULT_MAX_PAGES = 20
MAX_MAX_PAGES = 40


def pager_links(page, base_url):
    """Map page number -> absolute URL for href-based CBPT pagers."""
    links = {}
    for href in PAGER_HREF.findall(page):
        match = PAGER_PAGE_NUM.search(href)
        if not match:
            continue
        number = int(match.group(1))
        if number < 2 or number in links:
            continue
        links[number] = urljoin(base_url, html_lib.unescape(href))
    return links


def pager_identity(url):
    """Return the yearId/issueId carried by a pager URL (only non-empty values)."""
    query = parse_qs(urlsplit(url).query)
    identity = {}
    for name in PAGER_IDENTITY_PARAMS:
        value = (query.get(name) or [""])[0].strip()
        if value:
            identity[name] = value
    return identity


def normalize_max_pages(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("max_pages_per_journal must be an integer between 1 and 40")
    return max(1, min(MAX_MAX_PAGES, number))


def read_current_issue(base_url, timeout, max_pages=DEFAULT_MAX_PAGES, warn=None):
    """Read type_benqi, following href-based pagers within the current issue.

    `max_pages` caps total pages (first page included); the pager's own last
    page number caps it further. From page 2 on, yearId/issueId must match the
    first pager URL, otherwise paging stops so back issues cannot leak in.
    """
    first_url = current_issue_url(base_url)
    first_html = fetch_html(first_url, timeout)
    parser = PaperParser()
    parser.feed(first_html)
    papers = list(parser.papers)
    seen = {paper["url"] for paper in papers}
    links = pager_links(first_html, first_url)
    if not links:
        # A pager that renders only pageNum=1 is a real single-page issue, not
        # JS pagination; only warn when no pageNum href exists at all.
        if ("paperPage_list" in first_html and not PAGER_HREF.search(first_html)
                and warn is not None):
            warn(f"当期页含 paperPage_list 控件但无 href 分页链接，可能由 JS 渲染分页；"
                 f"仅采集第 1 页 {len(papers)} 条")
        return papers
    expected = {}
    for number in sorted(links):
        expected = pager_identity(links[number])
        if expected:
            break
    last_page = min(normalize_max_pages(max_pages), max(links))
    for number in sorted(links):
        if number > last_page:
            continue
        url = links[number]
        if expected:
            found = pager_identity(url)
            mismatched = [name for name, value in expected.items()
                          if found.get(name) and found[name] != value]
            if mismatched:
                if warn is not None:
                    warn(f"第 {number} 页 {'/'.join(mismatched)} 与当期不一致，"
                         f"停止翻页（已采集 {len(papers)} 条）")
                break
        page_parser = PaperParser()
        page_parser.feed(fetch_html(url, timeout))
        for paper in page_parser.papers:
            if paper["url"] in seen:
                continue
            seen.add(paper["url"])
            papers.append(paper)
    return papers


def paper_item(key, journal, base_url, record):
    url = urljoin(base_url, record["url"])
    query = parse_qs(urlsplit(url).query)
    external_id = (str(record.get("external_id") or "").strip()
                   or (query.get("paperID") or [""])[0]
                   or url.rstrip("/").split("/")[-1])
    if not re.fullmatch(r"[\w-]{6,128}", external_id):
        return None
    return {
        "journal_key": key, "journal_name": journal["name"][:255],
        "journal_url": journal["url"], "external_id": external_id,
        "title": record["title"][:1000], "url": url,
        "authors": record["authors"] or None,
        "abstract": clean_abstract(record.get("abstract"), record["title"]),
        "issue": (record.get("issue") or "")[:255] or None,
    }


def collect(request_data, journals):
    parameters = request_data.get("parameters") or {}
    collect_mode = parameters.get("collect_mode", "keywords")
    if collect_mode not in {"keywords", "latest_issue"}:
        raise ValueError(f"unsupported collect_mode: {collect_mode}")
    keys = parameters.get("journal_keys") or []
    if not keys:
        raise ValueError("journal_keys cannot be empty")
    query = request_data["query"].strip()
    if not query:
        raise ValueError("query cannot be empty")
    limit = request_data["limit"]
    per_journal_limit = parameters.get("per_journal_limit", 20)
    timeout = parameters.get("timeout_seconds", 20)
    enrich_abstract = parameters.get("enrich_abstract", True)
    if not isinstance(enrich_abstract, bool):
        enrich_abstract = str(enrich_abstract).strip().lower() not in {"false", "0", "no", "off"}
    try:
        abstract_enrich_limit = int(parameters.get("abstract_enrich_limit", 5))
    except (TypeError, ValueError):
        raise ValueError("abstract_enrich_limit must be an integer between 0 and 10")
    abstract_enrich_limit = max(0, min(10, abstract_enrich_limit))
    max_pages = normalize_max_pages(parameters.get("max_pages_per_journal", DEFAULT_MAX_PAGES))
    items, warnings = [], []
    successful = 0
    for index, key in enumerate(keys[:limit]):
        if len(items) >= limit:
            break
        journal_limit = min(per_journal_limit, limit // min(len(keys), limit) + int(index < limit % min(len(keys), limit)))
        journal = journals.get(key)
        if journal is None:
            warnings.append(f"Unknown journal key: {key}")
            continue
        host = urlsplit(journal["url"]).hostname or ""
        if not host.endswith(".cbpt.cnki.net"):
            warnings.append(f"Unsupported journal host: {host}")
            continue
        if host.startswith("www."):
            host = host[4:]
        base_url = "https://" + host
        seen = set()

        def warn(message, key=key, journal=journal):
            warnings.append(f"{key} ({journal['name']}): {message}")

        try:
            if collect_mode == "latest_issue":
                current_url = journal.get("current_url")
                is_wk = bool(current_url) and "WebPublication" in current_url
                opener = make_opener() if is_wk else None
                records = (read_wkd_current(current_url, timeout, opener, warn) if is_wk
                           else read_current_issue(base_url, timeout, max_pages, warn))
                journal_items = []
                for record in records:
                    item = paper_item(key, journal, base_url, record)
                    if item is None or item["external_id"] in seen:
                        continue
                    seen.add(item["external_id"])
                    items.append(item)
                    journal_items.append(item)
                    if len(seen) >= journal_limit or len(items) >= limit:
                        break
                if opener is not None and enrich_abstract and abstract_enrich_limit:
                    enrich_wk_abstracts(key, journal, journal_items, opener, timeout,
                                        abstract_enrich_limit, warnings)
                successful += 1
                continue
            for page in range(1, min(100, journal_limit) + 1):
                records = read_page(base_url, query, page, timeout)
                if not records:
                    break
                page_added = 0
                for record in records:
                    item = paper_item(key, journal, base_url, record)
                    if item is None or item["external_id"] in seen:
                        continue
                    seen.add(item["external_id"])
                    items.append(item)
                    page_added += 1
                    if len(seen) >= journal_limit or len(items) >= limit:
                        break
                if page_added == 0 or len(seen) >= journal_limit or len(items) >= limit:
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
    result = {
        "protocol_version": "1.0", "execution_id": execution_id,
        "status": status, "item_count": len(items), "next_cursor": None,
        "has_more": False, "warnings": warnings, "error": error,
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
        rows = json.loads((Path(__file__).with_name("journals.json")).read_text(encoding="utf-8"))
        items, warnings, successful = collect(request_data, {row["journal_key"]: row for row in rows})
        status = "partial" if successful and warnings else "completed" if successful else "failed"
        error = None if successful else {"code": "ALL_JOURNALS_FAILED", "message": "; ".join(warnings)[:2000], "retryable": True}
        write_output(output, request_data["execution_id"], items, status, warnings, error)
        return 0 if successful else 1
    except Exception as exc:
        write_output(output, request_data.get("execution_id", ""), [], "failed", [],
                     {"code": "CRAWLER_ERROR", "message": f"{type(exc).__name__}: {exc}", "retryable": False})
        return 1


if __name__ == "__main__":
    sys.exit(main())
