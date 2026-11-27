from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from http.cookiejar import CookieJar
from pathlib import Path
from collections import defaultdict
from urllib.error import HTTPError
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


USER_AGENT = "Mozilla/5.0 (compatible; JournalMetadataCollector/1.0)"
MAX_RESPONSE = 3_000_000
ABSTRACT_MIN_LENGTH = 40
ABSTRACT_MAX_LENGTH = 5000
ABSTRACT_META_MIN_LENGTH = 100
ABSTRACT_ENRICH_DELAY = 1.6
ABSTRACT_PLACEHOLDERS = {"无", "暂无", "暂无摘要", "无摘要", "没有摘要", "摘要", "abstract", "n/a", "na", "none", "null", "undefined", "-"}
ABSTRACT_CUT = re.compile(r"(?:【\s*关键词\s*】|关键词|关键字|Key\s*words?|参考文献|References|引用本文|基金项目|作者简介|收稿日期|中图分类号|文章编号|DOI\s*[:：]|英文摘要)", re.I)
MAX_PAGINATION_PAGES = 20
AUTO_PAGINATION_PAGES = 10
PAGE_PARAM_NAME = re.compile(
    r"^(?:page|p|pn|pg|paged|pageno|pagenum|page_no|page_num|pageindex|page_index|curpage|currentpage|pageid|page_id|apage\d*)$",
    re.I,
)
FORBIDDEN_PARAMS = {
    "year", "yearid", "quarter", "quarterid", "issue", "issueid", "issueno", "issuetype",
    "volume", "vol", "catename", "topcatename",
}
ISSUE_MARKER = re.compile(r"(20\d{2}\s*年\s*第?\s*\d+\s*期)")
PDF_URL = re.compile(r"\.pdf(?:$|[?#])|/pdf/", re.I)
OPENER = build_opener(HTTPCookieProcessor(CookieJar()))
ARTICLE_LINK = re.compile(r'display_son\.aspx|Issue_Content\.aspx|viewmulu\.aspx|DArticle\.aspx|/article/doi/|/article/abstract/|/info/\d+/\d+\.(?:htm|html)|/article/\d+\.html|/\d{4}/\d{2}/\d{2}/[0-9a-f]{16,}\.html|/client/paper/|/CN/abstract/abstract|_upload/article/files/[^"\']+\.pdf|/CN/10\.\d{4,9}/|/EN/10\.\d{4,9}/|/CN/Y\d{4}/|/art/\d{4}/art_[0-9a-f]+\.html|/portal/article/|/html/down/|/view_abstract\.aspx|/articlecontent\.aspx|/paperDigest\.aspx\?paperID=|/CN/\d{6,}|/cmaid/|/UploadFile/Issue/|/Magazine/Show', re.I)
NAV_TITLE = re.compile(r"^(首页|上一页|下一页|更多|过刊|当期目录|本期目录|联系我们|学报编辑部|登录|注册)", re.I)
DIRECTORY_TITLE = re.compile(r"(?:目录|目次|封面|封底|征稿|启事|稿约)(?:\s|$)")
LABEL_TITLE = re.compile(r"^\[[^\]]{1,40}\]$")
LABEL_ONLY = {"HTML Full Text", "PDF", "PDF全文", "ESM", "Abstract", "摘要"}


def clean(value):
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).replace("#br#", " ")
    return " ".join(text.replace("&nbsp;", " ").split())


def normalize_url(value):
    if any(ord(ch) > 127 or ch == " " for ch in value):
        return quote(value, safe=":/?#[]@!$&'()*+,;=%")
    return value


def normalize_abstract(value, title=None):
    if isinstance(value, (dict, list)):
        if isinstance(value, dict):
            values = [value.get(key) for key in ("text", "content", "value", "cn", "zh", "abstract", "summary")]
        else:
            values = value
        parts = [part for part in (normalize_abstract(entry, title) for entry in values) if part]
        return " ".join(parts)[:ABSTRACT_MAX_LENGTH] or None
    text = clean(value)
    text = re.sub(r"^(?:摘\s*要|Abstract)\s*[:：]\s*", "", text, flags=re.I)
    text = re.sub(r"^[\s:：\-—–_=*·|]+", "", text).strip()
    if len(text) < ABSTRACT_MIN_LENGTH:
        return None
    lowered = text.strip(" .。:：;；").lower()
    if lowered in ABSTRACT_PLACEHOLDERS or lowered.startswith(("暂无摘要", "无摘要", "暂无内容", "没有摘要")):
        return None
    if title and lowered == clean(title).strip(" .。:：;；").lower():
        return None
    return text[:ABSTRACT_MAX_LENGTH]


def page_text(page):
    page = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", page, flags=re.I | re.S)
    return clean(page)


def extract_zhaiyaojs(page, title=None):
    marker = re.search(r'<div\b[^>]+class=["\'][^"\']*zhaiyaojs[^"\']*["\'][^>]*>', page, re.I)
    if not marker:
        return None
    region = page[marker.end():]
    end = re.search(r'class=["\'][^"\']*main_content_center_left_zhengwen_bao', region, re.I)
    if end:
        region = region[:end.start()]
    else:
        region = region[:120_000]
    for block in re.finditer(
        r'<div\b([^>]*class=["\'][^"\']*\bmain_content_center_left_zhengwen\b[^"\']*["\'][^>]*)>(.*?)</div>',
        region, re.I | re.S,
    ):
        attrs, body = block.group(1), block.group(2)
        if "margin-bottom" not in attrs:
            continue
        text = clean(body)
        if re.search(r"AuthorUl|作者简介|通讯作者|E-?mail|^作\s*者", text, re.I):
            continue
        text = re.sub(r"^摘\s*要\s*[:：]\s*", "", text)
        cut = re.search(r"\bAbstract\b", text)
        if cut:
            text = text[:cut.start()]
        cut = ABSTRACT_CUT.search(text)
        if cut:
            text = text[:cut.start()]
        abstract = normalize_abstract(text, title)
        if abstract:
            return abstract
    return None


def extract_bracketed_abstract(page, title=None):
    match = re.search(r"【\s*摘\s*要\s*】", page)
    if not match:
        return None
    segment = page[match.end():match.end() + ABSTRACT_MAX_LENGTH * 3]
    cut = re.search(r"【\s*(?:关键词|关键字|作者|中图分类号|文献标识码|文章编号|Abstract)\s*】", segment, re.I)
    if cut:
        segment = segment[:cut.start()]
    text = clean(segment)
    cut = ABSTRACT_CUT.search(text)
    if cut:
        text = text[:cut.start()]
    return normalize_abstract(text, title)


def extract_meta_description(page, title=None):
    for meta in re.finditer(r'<meta\b[^>]*(?:name|property)=["\']description["\'][^>]*>', page, re.I):
        content = re.search(r'content=["\']([^"\']*)["\']', meta.group(0), re.I)
        if not content:
            continue
        abstract = normalize_abstract(content.group(1), title)
        # 只接受明显的正文摘要，避免把 SEO 短描述当成摘要
        if abstract and len(abstract) > ABSTRACT_META_MIN_LENGTH:
            return abstract
    return None


def extract_abstract(page, title=None):
    if not page:
        return None
    for meta in re.finditer(r'<meta\b[^>]*(?:name|property)=["\']citation_abstract["\'][^>]*>', page, re.I):
        content = re.search(r'content=["\']([^"\']*)["\']', meta.group(0), re.I)
        if content:
            abstract = normalize_abstract(content.group(1), title)
            if abstract:
                return abstract
    containers = (
        r'<(?:p|div)[^>]+(?:class|id)=["\'][^"\']*(?:CnAbstractValue|EnAbstractValue)[^"\']*["\'][^>]*>(.*?)</(?:p|div)>',
        r'<p[^>]+class=["\'][^"\']*in_abst[^"\']*["\'][^>]*>\s*摘\s*要\s*</p>\s*<p[^>]*>(.*?)</p>',
        r'<(?:div|section)[^>]+class=["\'](?:[^"\']*\s)?(?:article-abstract|article_abstract|abstract-content|abstract-body|abstractBody|abstract-text|abstractText)(?:\s[^"\']*)?["\'][^>]*>(.*?)</(?:div|section)>',
        r'<(?:div|section)[^>]+class=["\'](?:[^"\']*\s)?abstract(?:\s[^"\']*)?["\'][^>]*>(.*?)</(?:div|section)>',
    )
    for pattern in containers:
        for match in re.finditer(pattern, page, re.I | re.S):
            abstract = normalize_abstract(match.group(1), title)
            if abstract:
                return abstract
    for extractor in (extract_zhaiyaojs, extract_bracketed_abstract):
        abstract = extractor(page, title)
        if abstract:
            return abstract
    text = page_text(page)
    for pattern in (r"摘\s*要\s*[:：]", r"Abstract\s*[:：]"):
        for match in re.finditer(pattern, text, re.I):
            segment = text[match.end():match.end() + ABSTRACT_MAX_LENGTH * 2]
            cut = ABSTRACT_CUT.search(segment)
            if cut:
                segment = segment[:cut.start()]
            abstract = normalize_abstract(segment, title)
            if abstract:
                return abstract
    return extract_meta_description(page, title)


def record_abstract(record, fields, title):
    names = []
    if fields.get("abstract"):
        names.append(fields["abstract"])
    names.extend(["abstract", "abstractinfoCn", "abstractInfoCn", "abstractCn", "abstractCN", "summary",
                  "abstractText", "abstract_text", "abstractEn", "abstractinfoEn"])
    for name in names:
        if name in record:
            abstract = normalize_abstract(record.get(name), title)
            if abstract:
                return abstract
    return None


def enrich_abstracts(items, timeout, limit, delay=ABSTRACT_ENRICH_DELAY, user_agent=None):
    attempts = 0
    for item in items:
        if attempts >= limit:
            break
        if item.get("abstract") or not item.get("url") or PDF_URL.search(item["url"]):
            continue
        if attempts and delay:
            time.sleep(delay)
        attempts += 1
        try:
            kwargs = {"user_agent": user_agent} if user_agent else {}
            abstract = extract_abstract(fetch_text(item["url"], timeout, **kwargs), item.get("title"))
        except Exception:
            continue
        if abstract and not item.get("abstract"):
            item["abstract"] = abstract
    return attempts


def decode_html(raw, charset):
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    if not charset or charset.lower() in {"iso-8859-1", "latin-1"}:
        match = re.search(rb"charset\s*=\s*['\"]?([A-Za-z0-9_-]+)", raw[:4096], re.I)
        if match:
            charset = match.group(1).decode("ascii")
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def read_page(journal, timeout):
    limit = int(journal.get("max_response_bytes") or MAX_RESPONSE)
    request = Request(journal["current_url"], headers={
        "User-Agent": journal.get("user_agent") or USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    with OPENER.open(request, timeout=timeout) as response:
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError(f"response exceeds {limit} bytes")
        charset = response.headers.get_content_charset()
    return decode_html(raw, charset)


def fetch_text(url, timeout, accept="text/html,application/xhtml+xml", user_agent=None):
    request = Request(url, headers={"User-Agent": user_agent or USER_AGENT, "Accept": accept})
    with OPENER.open(request, timeout=timeout) as response:
        if response.headers.get_content_type() == "application/pdf":
            raise ValueError("PDF response is not supported")
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        charset = response.headers.get_content_charset()
    return decode_html(raw, charset)


def read_json(journal, timeout):
    config = journal["json_api"]
    url = config.get("url")
    if config.get("params_from_page"):
        source = config["params_from_page"]
        page = fetch_text(source["url"], timeout)
        params = {}
        for name, pattern in source["regex"].items():
            match = re.search(pattern, page, re.S)
            if not match:
                raise ValueError(f"json api param missing: {name}")
            params[name] = match.group(1)
        if config.get("api_url_template"):
            url = config["api_url_template"].format_map(defaultdict(str, params))
    if not url:
        url = journal["current_url"]
    text = fetch_text(url, timeout, "application/json, text/plain, */*")
    return json.loads(text)


def format_authors(value):
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("authorName") or item.get("authorNameCn") or (
                    str(item.get("surNameCn") or "") + str(item.get("givenNamesCn") or ""))
            else:
                name = clean(item)
            if name:
                names.append(str(name).strip())
        return ", ".join(names) or None
    return clean(value) or None


def accept_title(title, journal=None):
    if len(title) < 8 or NAV_TITLE.search(title) or DIRECTORY_TITLE.search(title):
        return False
    if LABEL_TITLE.match(title) or title in LABEL_ONLY or re.match(r"^(?:摘要|评论|点击|下载|浏览|收藏)\s*[（(:：]", title):
        return False
    if title.startswith("[摘要]") or "目录" in title and re.search(r"20\d{2}年第\s*\d+\s*期", title):
        return False
    if any(value in title for value in ("中国人权信息", "微信公众号", "研究中心")):
        return False
    if re.search(r"(?:团队介绍|创新团队)$", title):
        return False
    relaxed = bool(journal and journal.get("relaxed_title_filter"))
    if not relaxed and re.search(r"(通知|征文|启事|招聘|声明|新闻|报道|动态|会议|论坛|一行|来访|编辑部|学报编辑部|编委会|发刊词|预出版|座谈会|研讨会|我校|入选|倡议|喜报|祝贺|讲座|招标|采购|公示|^NO\.|电子版查阅|重要提示)", title):
        return False
    return True


def build_item(journal, title, article_url, external_id, **extra):
    item = {
        "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
        "journal_url": journal["url"], "external_id": str(external_id)[:128],
        "title": title[:1000], "url": article_url,
        "authors": None, "abstract": None, "doi": None,
        "year": None, "issue": None, "source_api": "custom_toc",
    }
    item.update(extra)
    return item


def slice_section(page, journal):
    start_pattern = journal.get("section_start_regex")
    last_pattern = journal.get("last_section_regex")
    if start_pattern:
        matches = list(re.finditer(start_pattern, page, re.S | re.I))
        if not matches:
            raise ValueError("section start marker not found")
        page = page[matches[0].start():]
    elif last_pattern:
        matches = list(re.finditer(last_pattern, page, re.S | re.I))
        if not matches:
            raise ValueError("last section marker not found")
        page = page[matches[-1].start():]
    end_pattern = journal.get("section_end_regex")
    if end_pattern:
        match = re.search(end_pattern, page, re.S | re.I)
        if match:
            page = page[:match.start()]
    return page


def parse_toc(page, journal):
    items, seen = [], set()
    page = slice_section(page, journal)
    pattern = re.compile(journal["article_link_regex"], re.I) if journal.get("article_link_regex") else ARTICLE_LINK
    for href, text in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.I | re.S):
        title = re.sub(r"\s+\*$", "", clean(text))
        title = re.sub(r"\s*(?:浏览次数|点击次数|附件下载).*$", "", title).strip()
        raw_url = urljoin(journal.get("link_base") or journal["current_url"], html.unescape(href).strip())
        if not pattern.search(raw_url):
            continue
        article_url = normalize_url(raw_url)
        if not accept_title(title, journal):
            continue
        if article_url in seen:
            continue
        seen.add(article_url)
        query = parse_qs(urlsplit(article_url).query)
        doi_match = re.search(r"/(?:article/doi|E[NS])/(10\.\d{4,9}/[^/?#]+)", article_url, re.I)
        path_id = re.search(r"/info/\d+/(\d+)\.(?:htm|html)", article_url, re.I) or re.search(r"/article/(\d+)\.html", article_url, re.I) or re.search(r"/client/paper/([^/?#]+)", article_url, re.I) or re.search(r"/CN/abstract/([^/?#]+)", article_url, re.I) or re.search(r"/article/abstract/([^/?#]+)", article_url, re.I) or re.search(r"/(?:CN|EN)/(10\.\d{4,9}/[^?#]+)", article_url, re.I) or re.search(r"/CN/(Y\d{4}/V[^/?#]*/I[^/?#]*/\d+)", article_url, re.I) or re.search(r"/Data/Acrtice/(\d+)", article_url, re.I) or re.search(r"/art/\d{4}/(art_[0-9a-f]+)\.html", article_url, re.I) or re.search(r"/html/down/[^/]+/(\d+)\.html", article_url, re.I) or re.search(r"/CN/(\d{6,})", article_url, re.I) or re.search(r"/cmaid/(\d+)", article_url, re.I)
        external_id = next((query[key][0] for key in ("id", "ID", "mid", "Nid", "file_no", "paperID") if query.get(key)), None) or (doi_match.group(1) if doi_match else None) or (path_id.group(1) if path_id else None) or (article_url.rstrip("/").split("/")[-1][:128] if article_url.lower().endswith(".pdf") else None)
        external_id = external_id or hashlib.sha1(article_url.encode("utf-8")).hexdigest()[:16]
        items.append(build_item(journal, title, article_url, external_id,
                                doi=doi_match.group(1) if doi_match else None))
    return items


def parse_json_toc(payload, journal):
    config = journal["json_api"]
    fields = config.get("fields") or {}
    data = payload
    for part in filter(None, str(config.get("data_path", "")).split(".")):
        data = data.get(part) if isinstance(data, dict) else None
    groups = data.values() if isinstance(data, dict) else [data]
    items, seen = [], set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for record in group:
            if not isinstance(record, dict):
                continue
            title = clean(record.get(fields.get("title", "title")))
            if config.get("url_template"):
                article_url = config["url_template"].format_map(defaultdict(str, record)).strip()
            else:
                article_url = str(record.get(fields.get("url", "url")) or "").strip() if fields.get("url") else ""
            if not article_url.startswith(("http://", "https://")) and article_url:
                article_url = urljoin(config.get("base") or journal.get("current_url", ""), article_url)
            if not accept_title(title, journal) or not article_url.startswith(("http://", "https://")) or article_url in seen:
                continue
            seen.add(article_url)
            doi = clean(record.get(fields.get("doi", "doi"))) or None
            issue_no = clean(record.get(fields.get("issue", "issue"))) or None
            year_text = str(record.get(fields.get("year", "year")) or "")
            year_match = re.search(r"(20\d{2})", year_text)
            year = int(year_match.group(1)) if year_match else None
            issue = f"{year}年第{issue_no}期" if year and issue_no else issue_no
            external_id = record.get(fields.get("id", "id")) or doi or hashlib.sha1(article_url.encode("utf-8")).hexdigest()[:16]
            items.append(build_item(
                journal, title, article_url, external_id,
                authors=format_authors(record.get(fields.get("authors", "authors"))),
                abstract=record_abstract(record, fields, title),
                doi=doi, year=year, issue=issue,
            ))
    return items


def resolve_issue_urls(journal, timeout):
    config = journal["issue_link"]
    pattern = re.compile(config["regex"])
    page = read_page(journal, timeout)
    urls = []
    for href in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\']', page, re.I):
        href = html.unescape(href).strip()
        if not pattern.search(href):
            continue
        url = urljoin(config.get("base") or journal["current_url"], href)
        if url not in urls:
            urls.append(url)
    if not urls:
        raise ValueError("latest issue link not found")
    if config.get("select") == "latest":
        def issue_rank(url):
            for pattern in (r"/(20\d{2})nian/di(\d+)qi", r"/(20\d{2})[_-](\d+)(?:\D|$)"):
                match = re.search(pattern, url, re.I)
                if match:
                    return int(match.group(1)), int(match.group(2))
            return (-1, -1)
        # 过刊索引若按年/期升序排列，按 URL 中的年、期数字取最新；非期次链接保持原顺序。
        urls.sort(key=issue_rank, reverse=True)
    return urls


def parse_pair_toc(page, journal):
    config = journal["pair_link"]
    page = slice_section(page, journal)
    row_re = re.compile(config["row_regex"], re.I | re.S)
    title_re = re.compile(config["title_regex"], re.I | re.S)
    link_re = re.compile(config["link_regex"], re.I | re.S)
    items, seen = [], set()
    for row in row_re.finditer(page):
        block = row.group(0)
        title_match, link_match = title_re.search(block), link_re.search(block)
        if not title_match or not link_match:
            continue
        title = clean(title_match.group(1))
        href = html.unescape(link_match.group(1)).strip()
        if config.get("url_template"):
            article_url = config["url_template"].format(*link_match.groups())
        else:
            article_url = urljoin(journal.get("link_base") or journal["current_url"], href)
        if not accept_title(title, journal) or article_url in seen:
            continue
        seen.add(article_url)
        query = parse_qs(urlsplit(article_url).query)
        doi_match = re.search(r"/(?:article/doi|E[NS])/(10\.\d{4,9}/[^/?#]+)", article_url, re.I)
        path_id = re.search(r"/CN/abstract/abstract([^/?#]+)\.shtml", article_url, re.I) or re.search(r"/abstract/([^/?#]+)\.shtml", article_url, re.I) or re.search(r"/article/abstract/([^/?#]+)", article_url, re.I) or re.search(r"/CN/(Y\d{4}/V[^/?#]*/I[^/?#]*/\d+)", article_url, re.I) or re.search(r"/Data/Acrtice/(\d+)", article_url, re.I)
        external_id = next((query[key][0] for key in ("id", "ID", "mid", "Nid", "file_no", "paperID") if query.get(key)), None) or (doi_match.group(1) if doi_match else None) or (path_id.group(1) if path_id else None) or hashlib.sha1(article_url.encode("utf-8")).hexdigest()[:16]
        items.append(build_item(journal, title, article_url, external_id,
                                doi=doi_match.group(1) if doi_match else None))
    return items


def parse_onclick_toc(page, journal):
    config = journal["onclick_link"]
    pattern = re.compile(config["regex"])
    items, seen = [], set()
    for attrs, text in re.findall(r'<a\b([^>]*)>(.*?)</a>', page, re.I | re.S):
        match = pattern.search(attrs)
        if not match:
            continue
        title = clean(text)
        article_url = config["url_template"].format(*match.groups())
        if not accept_title(title, journal) or article_url in seen:
            continue
        seen.add(article_url)
        external_id = match.group(1) if match.groups() else hashlib.sha1(article_url.encode("utf-8")).hexdigest()[:16]
        items.append(build_item(journal, title, article_url, external_id))
    return items


def toc_mode(journal):
    if journal.get("json_api"):
        return "json"
    if journal.get("onclick_link"):
        return "onclick"
    if journal.get("pair_link"):
        return "pair"
    if journal.get("issue_link"):
        return "issue"
    return "plain"


def parse_toc_content(content, journal, mode):
    if mode == "json":
        return parse_json_toc(content, journal)
    if mode == "onclick":
        return parse_onclick_toc(content, journal)
    if mode == "pair":
        return parse_pair_toc(content, journal)
    return parse_toc(content, journal)


def normalize_param(name):
    return re.sub(r"[-_\s]", "", str(name)).lower()


def build_page_template(base_url, param):
    parts = urlsplit(base_url)
    pairs = [(name, value) for name, value in parse_qsl(parts.query, keep_blank_values=True) if name != param]
    pairs.append((param, "{page}"))
    query = urlencode(pairs).replace("%7Bpage%7D", "{page}")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def discover_pagination(page, base_url):
    """从当期首页的链接发现“仅页码参数不同”的安全翻页模板。"""
    if not page or not base_url:
        return None, 0
    base = urlsplit(base_url)
    if base.scheme not in {"http", "https"} or not base.path:
        return None, 0
    base_map = dict(parse_qsl(base.query, keep_blank_values=True))
    base_page_params = [name for name in base_map if PAGE_PARAM_NAME.match(name)]
    found = defaultdict(set)
    for href in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\']', page, re.I):
        href = html.unescape(href).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        try:
            target = urlsplit(urljoin(base_url, href))
        except ValueError:
            continue
        if target.scheme not in {"http", "https"} or target.netloc.lower() != base.netloc.lower():
            continue
        if target.path.rstrip("/") != base.path.rstrip("/"):
            continue
        pairs = parse_qsl(target.query, keep_blank_values=True)
        names = [name for name, _ in pairs]
        if len(names) != len(set(names)):
            continue
        target_map = dict(pairs)
        if any(name not in target_map for name in base_map):
            continue
        page_params, rejected = [], False
        for name, value in pairs:
            if name in base_map and value == base_map[name]:
                continue
            if (normalize_param(name) in FORBIDDEN_PARAMS or not PAGE_PARAM_NAME.match(name)
                    or not value.isdigit() or (name not in base_map and base_page_params)):
                rejected = True
                break
            page_params.append(name)
        if rejected or len(page_params) != 1:
            continue
        number = int(target_map[page_params[0]])
        if 2 <= number <= MAX_PAGINATION_PAGES:
            found[page_params[0]].add(number)
    if not found:
        return None, 0
    param = max(found, key=lambda name: len(found[name]))
    numbers = found[param]
    if len(numbers) < 2:
        return None, 0
    return build_page_template(base_url, param), max(numbers)


def format_page_url(template, number):
    try:
        return template.format(page=number)
    except (KeyError, IndexError, ValueError):
        return str(template).replace("{page}", str(number))


def issue_markers(page):
    if not page:
        return set()
    return {re.sub(r"\s+", "", marker) for marker in ISSUE_MARKER.findall(page_text(page))[:20]}


def pagination_note(journal, message):
    return f"{journal.get('journal_key', '?')} ({journal.get('name', '?')}): PAGINATION_STOPPED {message}"


def extend_paged_items(rows, journal, timeout, mode="plain", first_page=None, budget=None, warnings=None):
    notes = warnings if warnings is not None else []
    config = journal.get("pagination")
    explicit = isinstance(config, dict) and bool(config)
    if not explicit and mode not in {"plain", "issue", "pair"}:
        return rows  # JSON/onclick 只接受显式配置
    base_url = journal.get("current_url") or ""
    markers = None
    if explicit:
        template = str(config.get("url_template") or "")
        if not template or "{page}" not in template:
            notes.append(pagination_note(journal, "SKIPPED missing url_template/{page}"))
            return rows
        try:
            start = max(2, int(config.get("start", 2)))
            requested = int(config.get("max_pages", MAX_PAGINATION_PAGES))
        except (TypeError, ValueError):
            notes.append(pagination_note(journal, "SKIPPED invalid start/max_pages"))
            return rows
        max_pages = min(requested, MAX_PAGINATION_PAGES)
        if requested > MAX_PAGINATION_PAGES:
            notes.append(pagination_note(journal, f"PAGE_LIMIT requested {requested} capped {MAX_PAGINATION_PAGES}"))
        base_url = str(config.get("base") or base_url)
    else:
        template, discovered = discover_pagination(first_page, base_url)
        if not template:
            return rows
        max_pages = min(discovered, AUTO_PAGINATION_PAGES)
        if discovered > AUTO_PAGINATION_PAGES:
            notes.append(pagination_note(journal, f"PAGE_LIMIT auto {discovered} capped {AUTO_PAGINATION_PAGES}"))
        start = 2
        markers = issue_markers(first_page)
    seen = {item["url"] for item in rows}
    seen_pages = set()
    if seen:
        seen_pages.add(hashlib.sha1("\n".join(sorted(seen)).encode("utf-8")).hexdigest())
    consecutive_errors = 0
    for number in range(start, max_pages + 1):
        if budget and len(rows) >= budget:
            break
        target = urljoin(base_url, format_page_url(template, number))
        target_parts, base_parts = urlsplit(target), urlsplit(base_url)
        allow_external = bool(explicit and config.get("allow_external_host"))
        if not target_parts.netloc or (target_parts.netloc.lower() != base_parts.netloc.lower() and not allow_external):
            notes.append(pagination_note(journal, f"SKIPPED host {target_parts.netloc}"))
            break
        if not explicit and target_parts.path.rstrip("/") != base_parts.path.rstrip("/"):
            notes.append(pagination_note(journal, f"SKIPPED path {target_parts.path}"))
            break
        try:
            probe = dict(journal)
            probe["current_url"] = target
            if mode == "json":
                content = json.loads(fetch_text(target, timeout, "application/json, text/plain, */*"))
            else:
                content = read_page(probe, timeout)
        except HTTPError as exc:
            notes.append(pagination_note(journal, f"HTTP {exc.code} page {number}"))
            break
        except Exception as exc:
            consecutive_errors += 1
            if consecutive_errors >= 2:
                notes.append(pagination_note(journal, f"2 连续异常 page {number} {type(exc).__name__}"))
                break
            continue
        try:
            items = parse_toc_content(content, journal if mode == "json" else probe, mode)
        except Exception as exc:
            consecutive_errors += 1
            if consecutive_errors >= 2:
                notes.append(pagination_note(journal, f"2 连续解析异常 page {number} {type(exc).__name__}"))
                break
            continue
        consecutive_errors = 0
        if markers and isinstance(content, str):
            current = issue_markers(content)
            if not current or not current <= markers:
                notes.append(pagination_note(journal, f"ISSUE_MARKER page {number}"))
                break
        fingerprint = hashlib.sha1("\n".join(sorted({item["url"] for item in items})).encode("utf-8")).hexdigest()
        if fingerprint in seen_pages:
            notes.append(pagination_note(journal, f"REPEATED_PAGE page {number}"))
            break
        seen_pages.add(fingerprint)
        new_items = [item for item in items if item["url"] not in seen]
        if not new_items:
            break
        for item in new_items:
            seen.add(item["url"])
            rows.append(item)
    return rows


def keyword_terms(request_data):
    terms = []
    for value in [request_data.get("query", "")] + list(request_data.get("aliases") or []):
        parts = [part.lower() for part in str(value or "").split() if part]
        if parts:
            terms.append(parts)
    return terms


def matches_keywords(item, terms):
    text = " ".join(str(item.get(field) or "") for field in ("title", "abstract", "authors", "doi")).lower()
    return any(all(part in text for part in parts) for parts in terms)


def collect(request_data, journals):
    params = request_data.get("parameters") or {}
    mode = params.get("collect_mode", "latest_issue")
    if mode not in {"latest_issue", "keywords"}:
        raise ValueError(f"unsupported collect_mode: {mode}")
    keys = params.get("journal_keys") or []
    if not keys or not request_data["query"].strip():
        raise ValueError("journal_keys and query must be nonempty")
    limit = request_data["limit"]
    per_journal = (min(params.get("per_journal_limit", 50), 200) if mode == "keywords"
                   else min(params.get("per_journal_limit", 50), max(1, (limit + len(keys) - 1) // len(keys))))
    terms = keyword_terms(request_data) if mode == "keywords" else []
    timeout = params.get("timeout_seconds", 20)
    enrich_abstract = params.get("enrich_abstract", True)
    if isinstance(enrich_abstract, str):
        enrich_abstract = enrich_abstract.strip().lower() not in {"false", "0", "no", "off"}
    try:
        abstract_enrich_limit = max(0, min(int(params.get("abstract_enrich_limit", 3)), 10))
    except (TypeError, ValueError):
        abstract_enrich_limit = 3
    items, warnings, successful = [], [], 0
    for key in keys:
        if len(items) >= limit:
            break
        journal = journals.get(key)
        if not journal:
            warnings.append(f"Unknown journal key: {key}")
            continue
        try:
            page_journal, issue_page = journal, None
            toc = toc_mode(journal)
            if journal.get("issue_link"):
                candidates = resolve_issue_urls(journal, timeout)
                config = journal["issue_link"]
                if config.get("require_articles"):
                    for candidate in candidates[:3]:
                        probe = dict(journal)
                        probe["current_url"] = candidate
                        issue_page = read_page(probe, timeout)
                        if len(parse_toc(issue_page, probe)) >= 2:
                            page_journal = probe
                            break
                    else:
                        raise ValueError("no issue with articles found")
                else:
                    page_journal = dict(journal)
                    page_journal["current_url"] = candidates[0]
            first_page = None
            page_budget = per_journal if mode == "latest_issue" else None
            if toc == "json":
                rows = parse_json_toc(read_json(journal, timeout), journal)
                rows = extend_paged_items(rows, journal, timeout, toc, None, page_budget, warnings)
            elif toc == "onclick":
                first_page = read_page(journal, timeout)
                rows = parse_onclick_toc(first_page, journal)
                rows = extend_paged_items(rows, journal, timeout, toc, first_page, page_budget, warnings)
            else:
                if issue_page is None:
                    issue_page = read_page(page_journal, timeout)
                first_page = issue_page
                rows = parse_toc_content(first_page, page_journal, toc)
                rows = extend_paged_items(rows, page_journal, timeout, toc, first_page, page_budget, warnings)
            added = []
            for item in rows:
                if mode == "keywords" and not matches_keywords(item, terms):
                    continue
                added.append(item)
                if len(added) >= per_journal or len(items) + len(added) >= limit:
                    break
            if mode == "latest_issue" and enrich_abstract and abstract_enrich_limit:
                enrich_abstracts(added, timeout, abstract_enrich_limit, user_agent=journal.get("user_agent"))
            items.extend(added)
            successful += 1
        except Exception as exc:
            warnings.append(f"{key} ({journal['name']}): {type(exc).__name__}: {exc}")
    if mode == "keywords" and not items:
        labels = [str(v).strip() for v in [request_data.get("query", "")] + list(request_data.get("aliases") or []) if str(v).strip()]
        warnings.append("当期目次中未匹配到关键词：" + " / ".join(labels))
    return items, warnings, successful


def write_output(output, execution_id, items, status, warnings, error=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    result = {"protocol_version": "1.0", "execution_id": execution_id, "status": status,
              "item_count": len(items), "next_cursor": None, "has_more": False,
              "warnings": warnings, "error": error}
    temporary = output / "result.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output / "result.json")


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
        write_output(Path(args.output), request_data.get("execution_id", ""), items, status, warnings, error)
        return 0 if successful else 1
    except Exception as exc:
        write_output(Path(args.output), request_data.get("execution_id", ""), [], "failed", [], {
            "code": "CRAWLER_ERROR", "message": f"{type(exc).__name__}: {exc}", "retryable": False})
        return 1


if __name__ == "__main__":
    sys.exit(main())
