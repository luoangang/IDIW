from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (compatible; JournalMetadataCollector/1.0)"
MAX_RESPONSE = 3_000_000
ABSTRACT_MIN_LENGTH = 50
ABSTRACT_MAX_LENGTH = 5000
DETAIL_DELAY = 2.0
RETRY_DELAY = 4.0
RETRY_HTTP_CODES = {502}
ENRICH_DEFAULT_LIMIT = 5
PDF_URL = re.compile(r"\.pdf(?:$|[?#])|/pdf/", re.I)
ABSTRACT_CUT = re.compile(
    r"(?:关键词|关键字|Key\s*words?|参考文献|References|引用本文|基金项目|作者简介|收稿日期|中图分类号|文章编号|英文摘要)", re.I)
ABSTRACT_PLACEHOLDERS = {"无", "暂无", "暂无摘要", "无摘要", "没有摘要", "摘要", "abstract", "n/a", "none", "null", "-"}
NOISE_TITLE = re.compile(
    r"^(?:\d{4,6}|(?:\d{4}年)?第?\d+期)?(?:封面|封二|封三|封底|目录|目次|封面和目录|封面、目录)$"
)


def read_legacy_issue(journal, timeout):
    base = journal["url"].rstrip("/")
    request = Request(base + "/", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        charset = response.headers.get_content_charset() if hasattr(response.headers, "get_content_charset") else None
        if not charset:
            content_type = response.headers.get("Content-Type", "") if hasattr(response.headers, "get") else ""
            match = re.search(r"charset\s*=\s*['\"]?([A-Za-z0-9_-]+)", content_type, re.I)
            charset = match.group(1) if match else None
    if not charset:
        match = re.search(rb"charset\s*=\s*['\"]?([A-Za-z0-9_-]+)", raw[:4000], re.I)
        charset = match.group(1).decode("ascii") if match else "utf-8"
    try:
        page = raw.decode(charset, errors="replace")
    except LookupError:
        page = raw.decode("gb18030", errors="replace")
    records, seen = [], set()
    for block in re.split(r'(?=<div\s+class=["\']item["\'])', page, flags=re.I)[1:]:
        title_link = re.search(
            r'<div[^>]*class=["\']title["\'][^>]*>.*?<a\b[^>]*href=["\']([^"\']*darticle\.aspx\?[^"\']*\bid=(\d+)[^"\']*)["\'][^>]*>(.*?)</a>',
            block, re.I | re.S,
        )
        if not title_link:
            continue
        article_id = title_link.group(2)
        title = clean(title_link.group(3))
        if not title or article_id in seen or NOISE_TITLE.match(title):
            continue
        seen.add(article_id)
        authors = re.search(r'<div[^>]*class=["\']authors["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        doi = re.search(r'(10\.\d{4,9}/[^\s"\'<>]+)', block, re.I)
        year, month = article_id[:4], article_id[4:6]
        issue = f"{year}年第{int(month)}期" if year.isdigit() and month.isdigit() else None
        records.append({
            "ArticleID": article_id,
            "Title": title,
            "AuthorsList": clean(authors.group(1)) if authors else "",
            "DOI": doi.group(1).rstrip(".,;") if doi else "",
            "Year": year,
            "YearIssue_No": issue or "",
            "_url": urljoin(base + "/", html.unescape(title_link.group(1))),
        })
    if not records:
        raise ValueError("UNSUPPORTED_TEMPLATE: no legacy paperopen articles")
    return records


def read_current_issue(journal, timeout):
    base = journal["url"].rstrip("/")
    try:
        request = Request(
            f"{base}/api/api/Web/LastIssueList?PageSize=0&IssueId=0",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Referer": base + "/"},
        )
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise ValueError("response exceeds 3 MB")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("Data"), list):
            raise ValueError("UNSUPPORTED_TEMPLATE: PaperOnce response lacks Data list")
        if data.get("IsSuccess") is False:
            raise ValueError(f"current issue rejected: {data.get('Message')}")
        return data["Data"]
    except (HTTPError, ValueError) as exc:
        if isinstance(exc, HTTPError) and exc.code != 404:
            raise
        return read_legacy_issue(journal, timeout)


def clean(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())


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
        content_type = response.headers.get_content_type() if hasattr(response.headers, "get_content_type") else ""
        if content_type == "application/pdf":
            raise ValueError("PDF response is not supported")
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        charset = response.headers.get_content_charset() if hasattr(response.headers, "get_content_charset") else None
    return decode_html(raw, charset)


def read_detail(url, timeout):
    try:
        return fetch_detail(url, timeout)
    except HTTPError as exc:
        if exc.code not in RETRY_HTTP_CODES:
            raise
        time.sleep(RETRY_DELAY)
        return fetch_detail(url, timeout)


def has_cjk(text):
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def normalize_abstract(value, title=None):
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
    cut = ABSTRACT_CUT.search(text)
    if cut:
        text = text[:cut.start()].strip()
    if len(text) < ABSTRACT_MIN_LENGTH:
        return None
    return text[:ABSTRACT_MAX_LENGTH]


def page_text(page):
    page = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", page, flags=re.I | re.S)
    return clean(page)


def extract_detail_abstract(page, title=None):
    if not page:
        return None
    span = re.search(r"<span\b[^>]*\bid\s*=\s*[\"']LbZY[\"'][^>]*>(.*?)</span>", page, re.I | re.S)
    if span:
        abstract = normalize_abstract(span.group(1), title)
        if abstract:
            return abstract
    text = page_text(page)
    candidates = []
    for pattern in (r"摘\s*要\s*[:：]", r"Abstract\s*[:：]"):
        for match in re.finditer(pattern, text, re.I):
            segment = text[match.end():match.end() + ABSTRACT_MAX_LENGTH * 2]
            cut = ABSTRACT_CUT.search(segment)
            if cut:
                segment = segment[:cut.start()]
            abstract = normalize_abstract(segment, title)
            if abstract:
                candidates.append(abstract)
    if not candidates:
        return None
    chinese = [value for value in candidates if has_cjk(value)]
    return (chinese or candidates)[0]


def enrich_params(params):
    enabled = params.get("enrich_abstract", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"false", "0", "no", "off"}
    try:
        limit = max(0, min(int(params.get("abstract_enrich_limit", ENRICH_DEFAULT_LIMIT)), 10))
    except (TypeError, ValueError):
        limit = ENRICH_DEFAULT_LIMIT
    return bool(enabled), limit


def detail_url(value):
    url = str(value or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    return url


def enrich_abstracts(items, timeout, limit, warnings, journal_name):
    attempts = 0
    for item in items:
        if attempts >= limit:
            break
        if item.get("abstract") or not item.get("url") or PDF_URL.search(item["url"]):
            continue
        url = detail_url(item["url"])
        if "/#/" in url:
            continue
        time.sleep(DETAIL_DELAY)
        attempts += 1
        try:
            abstract = extract_detail_abstract(read_detail(url, timeout), item.get("title"))
        except Exception as exc:
            warnings.append(f"{journal_name}: 摘要补采失败 {url}: {type(exc).__name__}")
            continue
        if abstract:
            item["abstract"] = abstract
        else:
            warnings.append(f"{journal_name}: 详情页无可用摘要 {url}")
    return attempts


def normalize(record, journal):
    if not isinstance(record, dict):
        return None
    title = clean(record.get("Title") or record.get("TitleE"))
    article_id = str(record.get("ArticleID") or "").strip()
    if not title or not article_id or NOISE_TITLE.match(title):
        return None
    base = journal["url"].rstrip("/")
    doi = clean(record.get("DOI"))
    date = str(record.get("PublishDate") or record.get("Year") or "")[:4]
    issue = clean(record.get("YearIssue_No") or record.get("IssueNum") or "") or None
    return {
        "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
        "journal_url": journal["url"], "external_id": article_id[:128],
        "title": title[:1000],
        "url": record.get("_url") or f"{base}/#/digest?ArticleID={quote(article_id)}",
        "authors": clean(record.get("AuthorsList") or record.get("AuthorsListE")) or None,
        "abstract": clean(record.get("Abstract_Chinese") or record.get("Abstract_English")) or None,
        "doi": doi[:255] or None, "year": int(date) if date.isdigit() else None,
        "issue": issue[:64] if issue else None, "source_api": "paperonce",
    }


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
        seen = set()
        try:
            rows = read_current_issue(journal, timeout)
            added = []
            for record in rows:
                item = normalize(record, journal)
                if mode == "keywords" and item and not matches_keywords(item, terms):
                    continue
                if item and item["external_id"] not in seen:
                    seen.add(item["external_id"])
                    added.append(item)
                    if len(seen) >= per_journal or len(items) + len(added) >= limit:
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
        write_output(Path(args.output), request_data["execution_id"], items, status, warnings, error)
        return 0 if successful else 1
    except Exception as exc:
        write_output(Path(args.output), request_data.get("execution_id", ""), [], "failed", [], {"code": "CRAWLER_ERROR", "message": f"{type(exc).__name__}: {exc}", "retryable": False})
        return 1


if __name__ == "__main__":
    sys.exit(main())
