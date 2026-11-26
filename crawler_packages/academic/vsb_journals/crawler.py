from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (compatible; JournalMetadataCollector/1.0)"
MAX_RESPONSE = 3_000_000
ABSTRACT_MIN_LENGTH = 40
ABSTRACT_MAX_LENGTH = 5000
META_MIN_LENGTH = 100
DETAIL_DELAY = 2.0
ENRICH_DEFAULT_LIMIT = 5
SKIP_DETAIL_HOSTS = {"kns.cnki.net"}
PDF_URL = re.compile(r"\.pdf(?:$|[?#])|/pdf/", re.I)
PDF_EMBED = re.compile(r"<(?:embed|iframe|object)\b[^>]*(?:application/pdf|\.pdf\b)", re.I)
ABSTRACT_CUT = re.compile(
    r"(?:关键词|关键字|Key\s*words?|参考文献|References|引用本文|基金项目|作者简介|收稿日期|中图分类号|文章编号|英文摘要)", re.I)
SITE_BLURB = re.compile(r"(?:创刊|主管|主办|邮发代号|ISSN|CN\s*\d{2}\s*-\s*\d{4}|投稿|期刊简介|杂志社|来源期刊|核心期刊)", re.I)
ABSTRACT_PLACEHOLDERS = {"无", "暂无", "暂无摘要", "无摘要", "没有摘要", "摘要", "abstract", "n/a", "none", "null", "-"}
ARTICLE_LINK = re.compile(r"/info/\d+/\d+\.(?:htm|html)|/qkdetail\?kid=|m\.chaoxing\.com/mqk/read/share_|kns\.cnki\.net/kcms2/article/abstract\?v=", re.I)
NAV_TITLE = re.compile(
    r"^(首页|网站首页|上一页|下一页|更多|登录|注册|联系我们|版权|简介|编委会|顾问委员会|编辑委员会|"
    r"当期目录|本期目录|过刊浏览|往期目录|网站地图|English|中文|PDF下载|收藏本页)\b",
    re.I,
)
DIRECTORY_TITLE = re.compile(r"(?:目录|封面|封底|征稿|启事|稿约)\s*$")


def clean(value):
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return " ".join(text.replace("&nbsp;", " ").split())


def decode_html(raw, charset):
    if not charset or charset.lower() in {"iso-8859-1", "latin-1"}:
        match = re.search(rb"charset\s*=\s*[\"']?([A-Za-z0-9_-]+)", raw[:4096], re.I)
        if match:
            charset = match.group(1).decode("ascii")
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("gb18030", errors="replace")


def fetch_detail(url, timeout):
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        if content_type == "application/pdf":
            raise ValueError("PDF response is not supported")
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        charset = response.headers.get_content_charset()
    return decode_html(raw, charset)


def page_text(page):
    page = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", page, flags=re.I | re.S)
    return clean(page)


def looks_pdf_only(page):
    return bool(PDF_EMBED.search(page)) and len(page_text(page)) < 400


def normalize_abstract(value, title=None, minimum=ABSTRACT_MIN_LENGTH):
    text = clean(value)
    text = re.sub(r"^(?:摘\s*要|Abstract)\s*[:：]\s*", "", text, flags=re.I)
    text = re.sub(r"^.*?[［【\[]\s*摘\s*要\s*[］】\]]\s*[:：]?\s*", "", text, flags=re.S)
    text = re.sub(r"^[\s:：\-—–_=*·|]+", "", text).strip()
    if len(text) < minimum:
        return None
    lowered = text.strip(" .。:：;；").lower()
    if lowered in ABSTRACT_PLACEHOLDERS or lowered.startswith(("暂无摘要", "无摘要", "暂无内容", "没有摘要")):
        return None
    if title and lowered == clean(title).strip(" .。:：;；").lower():
        return None
    cut = ABSTRACT_CUT.search(text)
    if cut:
        text = text[:cut.start()].strip()
    if len(text) < minimum:
        return None
    return text[:ABSTRACT_MAX_LENGTH]


def meta_description(page):
    tag = re.search(r"<meta\b[^>]*\bname\s*=\s*[\"']description[\"'][^>]*>", page, re.I | re.S)
    if not tag:
        return None
    content = re.search(r"content\s*=\s*([\"'])(.*?)\1", tag.group(0), re.I | re.S)
    return content.group(2) if content else None


def extract_detail_abstract(page, title=None):
    if not page:
        return None
    container = re.search(
        r"<(?:div|section)[^>]*class=[\"'][^\"']*\barticle-abstract\b[^\"']*[\"'][^>]*>(.*?)</(?:div|section)>",
        page, re.I | re.S)
    if container:
        abstract = normalize_abstract(container.group(1), title)
        if abstract:
            return abstract
    text = page_text(page)
    tag = re.search(r"[［【\[]\s*摘\s*要\s*[］】\]]\s*[:：]?(.*)", text)
    if tag:
        abstract = normalize_abstract(tag.group(1), title)
        if abstract:
            return abstract
    description = meta_description(page)
    if description and not SITE_BLURB.search(description):
        abstract = normalize_abstract(description, title, META_MIN_LENGTH + 1)
        if abstract:
            return abstract
    for match in re.finditer(r"摘\s*要\s*[:：]", text):
        abstract = normalize_abstract(text[match.end():match.end() + ABSTRACT_MAX_LENGTH * 2], title)
        if abstract:
            return abstract
    return None


def enrich_params(params):
    enabled = params.get("enrich_abstract", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"false", "0", "no", "off"}
    try:
        limit = max(0, min(int(params.get("abstract_enrich_limit", ENRICH_DEFAULT_LIMIT)), 10))
    except (TypeError, ValueError):
        limit = ENRICH_DEFAULT_LIMIT
    return bool(enabled), limit


def skip_detail(url):
    if PDF_URL.search(url):
        return True
    return (urlsplit(url).hostname or "").lower() in SKIP_DETAIL_HOSTS


def enrich_abstracts(items, timeout, limit, warnings, journal_name):
    attempts = 0
    for item in items:
        if attempts >= limit:
            break
        if item.get("abstract") or not item.get("url") or skip_detail(item["url"]):
            continue
        time.sleep(DETAIL_DELAY)
        attempts += 1
        try:
            page = fetch_detail(item["url"], timeout)
        except Exception as exc:
            warnings.append(f"{journal_name}: 摘要补采失败 {item['url']}: {type(exc).__name__}")
            continue
        if looks_pdf_only(page):
            warnings.append(f"{journal_name}: 仅 PDF 页面，跳过摘要补采 {item['url']}")
            continue
        abstract = extract_detail_abstract(page, item.get("title"))
        if abstract:
            item["abstract"] = abstract
        else:
            warnings.append(f"{journal_name}: 详情页无可用摘要 {item['url']}")
    return attempts


def read_page(journal, timeout):
    request = Request(
        journal["current_url"],
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        charset = response.headers.get_content_charset() or "utf-8"
    return decode_html(raw, charset)


def parse_region(page, journal):
    start = journal.get("section_start_regex")
    if not start:
        return page
    opening = re.search(start, page, re.I | re.S)
    if not opening:
        return page
    region = page[opening.start():]
    end = journal.get("section_end_regex")
    if end:
        closing = re.search(end, region, re.I | re.S)
        if closing:
            region = region[:closing.start()]
    return region


def parse_toc(page, journal):
    items, seen = [], set()
    page = parse_region(page, journal)
    link_pattern = re.compile(journal["article_link_regex"], re.I) if journal.get("article_link_regex") else ARTICLE_LINK
    for attrs, inner in re.findall(r"<a\b([^>]*)>(.*?)</a>", page, re.I | re.S):
        href = re.search(r"\bhref\s*=\s*[\"']([^\"']+)", attrs, re.I)
        if not href:
            continue
        link = html.unescape(href.group(1)).strip()
        title = clean(inner)
        heading = re.search(r"<h[1-4][^>]*>(.*?)</h[1-4]>", inner, re.I | re.S)
        if heading:
            title = clean(heading.group(1))
        if not title:
            attr = re.search(r"\b(?:alt|title)\s*=\s*[\"']([^\"']+)", attrs, re.I)
            title = clean(attr.group(1)) if attr else ""
        if len(title) < 8 or NAV_TITLE.search(title) or DIRECTORY_TITLE.search(title):
            continue
        if "目录" in title and re.search(r"(?:年第?\s*\d+\s*期|第\s*\d+\s*期|20\d{2})", title):
            continue
        title = re.sub(r"^\s*20\d{2}\s*年第\s*\d+\s*期[\s:：-]*", "", title)
        title = re.sub(r"^\s*[\[［][^\]］]{1,4}[\]］]\s*", "", title)
        article_url = urljoin(journal["current_url"], link)
        if not link_pattern.search(article_url):
            continue
        query_id = re.search(r"[?&](?:id|kid|v)=([^&#]+)", article_url, re.I)
        share_id = re.search(r"/share_([A-Za-z0-9]+)", article_url, re.I)
        path_id = re.search(r"/info/\d+/(\d+)\.(?:htm|html)", article_url, re.I)
        external_id = (query_id or share_id or path_id).group(1) if (query_id or share_id or path_id) else hashlib.sha1(article_url.encode("utf-8")).hexdigest()[:16]
        if external_id in seen:
            continue
        seen.add(external_id)
        items.append({
            "journal_key": journal["journal_key"],
            "journal_name": journal["name"][:255],
            "journal_url": journal["url"],
            "external_id": external_id[:128],
            "title": title[:1000],
            "url": article_url,
            "authors": None,
            "abstract": None,
            "doi": None,
            "year": None,
            "issue": None,
            "source_api": "official_toc",
        })
    return items


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
    query = request_data["query"].strip()
    if not keys or not query:
        raise ValueError("journal_keys and query must be nonempty")
    limit = request_data["limit"]
    per_journal = (min(params.get("per_journal_limit", 50), 200) if mode == "keywords"
                   else min(params.get("per_journal_limit", 50), max(1, (limit + len(keys) - 1) // len(keys))))
    terms = keyword_terms(request_data) if mode == "keywords" else []
    timeout = params.get("timeout_seconds", 20)
    enrich_abstract, abstract_enrich_limit = enrich_params(params)
    items, warnings, successful = [], [], 0
    for key in keys:
        if len(items) >= limit:
            break
        journal = journals.get(key)
        if not journal:
            warnings.append(f"Unknown journal key: {key}")
            continue
        try:
            rows = parse_toc(read_page(journal, timeout), journal)
            added = []
            for item in rows:
                if mode == "keywords" and not matches_keywords(item, terms):
                    continue
                added.append(item)
                if len(added) >= per_journal or len(items) + len(added) >= limit:
                    break
            if mode == "latest_issue" and enrich_abstract and abstract_enrich_limit:
                enrich_abstracts(added, timeout, abstract_enrich_limit, warnings, journal["name"])
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
    try:
        rows = json.loads(Path(__file__).with_name("journals.json").read_text(encoding="utf-8"))
        items, warnings, successful = collect(request_data, {row["journal_key"]: row for row in rows})
        status = "partial" if successful and warnings else "completed" if successful else "failed"
        error = None if successful else {
            "code": "ALL_JOURNALS_FAILED",
            "message": "; ".join(warnings)[:2000],
            "retryable": True,
        }
        write_output(Path(args.output), request_data["execution_id"], items, status, warnings, error)
        return 0 if successful else 1
    except Exception as exc:
        write_output(
            Path(args.output),
            request_data.get("execution_id", ""),
            [],
            "failed",
            [],
            {"code": "CRAWLER_ERROR", "message": f"{type(exc).__name__}: {exc}", "retryable": False},
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
