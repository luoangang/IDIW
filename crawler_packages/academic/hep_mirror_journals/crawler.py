from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (compatible; JournalMetadataCollector/1.0)"
MAX_RESPONSE = 3_000_000
ABSTRACT_MIN_LENGTH = 100
ABSTRACT_MAX_LENGTH = 5000
DETAIL_DELAY = 1.2
ENRICH_DEFAULT_LIMIT = 4
PDF_URL = re.compile(r"\.pdf(?:$|[?#])|/pdf/", re.I)
ABSTRACT_CUT = re.compile(
    r"(?:关键词|关键字|Key\s*words?|参考文献|References|引用本文|基金项目|作者简介|收稿日期|中图分类号|文章编号|英文摘要)", re.I)
ABSTRACT_PLACEHOLDERS = {"无", "暂无", "暂无摘要", "无摘要", "没有摘要", "摘要", "abstract", "n/a", "none", "null", "-"}
ARTICLE_LINK = re.compile(r"/CN/(?:10\.\d{4,9}/|\d{6,})", re.I)
NAV_TITLE = re.compile(
    r"^(首页|上一页|下一页|更多|过刊|当期目录|最新录用|期刊介绍|联系我们|E-mail|Email|"
    r"摘要|PDF|HTML|阅读排行|下载排行|引用排行|在线期刊|中国高校科技期刊集群服务平台|Adv search)",
    re.I,
)


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
        return raw.decode("utf-8", errors="replace")


def read_page(journal, timeout):
    request = Request(journal["current_url"], headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        charset = response.headers.get_content_charset() or "utf-8"
    return decode_html(raw, charset)


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


def normalize_abstract(value, title=None):
    text = clean(value)
    text = re.sub(r"^(?:摘\s*要|Abstract)\s*[:：]\s*", "", text, flags=re.I)
    text = re.sub(r"^[\s:：\-—–_=*·|]+", "", text).strip()
    if len(text) <= ABSTRACT_MIN_LENGTH:
        return None
    lowered = text.strip(" .。:：;；").lower()
    if lowered in ABSTRACT_PLACEHOLDERS or lowered.startswith(("暂无摘要", "无摘要", "暂无内容", "没有摘要")):
        return None
    if title and lowered == clean(title).strip(" .。:：;；").lower():
        return None
    cut = ABSTRACT_CUT.search(text)
    if cut:
        text = text[:cut.start()].strip()
    if len(text) <= ABSTRACT_MIN_LENGTH:
        return None
    return text[:ABSTRACT_MAX_LENGTH]


def meta_content(page, name):
    tag = re.search(
        r"<meta\b[^>]*(?:name|property)\s*=\s*[\"']" + re.escape(name) + r"[\"'][^>]*>", page, re.I | re.S)
    if not tag:
        return None
    content = re.search(r"content\s*=\s*([\"'])(.*?)\1", tag.group(0), re.I | re.S)
    return content.group(2) if content else None


def json_ld_abstract(page):
    for block in re.findall(r"<script\b[^>]*application/ld\+json[^>]*>(.*?)</script>", page, re.I | re.S):
        for raw in re.findall(r'"abstract"\s*:\s*"((?:[^"\\]|\\.)*)"', block, re.I):
            try:
                value = json.loads('"' + raw + '"')
            except ValueError:
                value = raw
            if value:
                return value
    return None


def extract_detail_abstract(page, title=None):
    if not page:
        return None
    for name in ("citation_abstract",):
        abstract = normalize_abstract(meta_content(page, name), title)
        if abstract:
            return abstract
    for name in ("description", "og:description", "twitter:description"):
        abstract = normalize_abstract(meta_content(page, name), title)
        if abstract:
            return abstract
    return normalize_abstract(json_ld_abstract(page), title)


def enrich_params(params):
    enabled = params.get("enrich_abstract", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"false", "0", "no", "off"}
    try:
        limit = max(0, min(int(params.get("abstract_enrich_limit", ENRICH_DEFAULT_LIMIT)), 10))
    except (TypeError, ValueError):
        limit = ENRICH_DEFAULT_LIMIT
    return bool(enabled), limit


def enrich_abstracts(items, timeout, limit, warnings, journal_name):
    attempts = 0
    for item in items:
        if attempts >= limit:
            break
        if item.get("abstract") or not item.get("url") or PDF_URL.search(item["url"]):
            continue
        time.sleep(DETAIL_DELAY)
        attempts += 1
        try:
            abstract = extract_detail_abstract(fetch_detail(item["url"], timeout), item.get("title"))
        except Exception as exc:
            warnings.append(f"{journal_name}: 摘要补采失败 {item.get('url')}: {type(exc).__name__}")
            continue
        if abstract:
            item["abstract"] = abstract
        else:
            warnings.append(f"{journal_name}: 详情页无可用摘要 {item.get('url')}")
    return attempts


def parse_toc(page, journal):
    items, seen = [], set()
    for href, text in re.findall(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", page, re.I | re.S):
        title = clean(text)
        article_url = urljoin(journal["current_url"], html.unescape(href).strip())
        if not ARTICLE_LINK.search(article_url):
            continue
        if len(title) < 8 or NAV_TITLE.search(title):
            continue
        if any(value in title for value in ("选题方向", "重点选题")):
            continue
        if title.startswith("http") or title in {"摘要", "HTML", "PDF全文"}:
            continue
        doi_id = re.search(r"/CN/(10\.\d{4,9}/[^?#]+)", article_url)
        numeric_id = re.search(r"/CN/(\d{6,})", article_url)
        external_id = (doi_id or numeric_id).group(1) if (doi_id or numeric_id) else hashlib.sha1(article_url.encode("utf-8")).hexdigest()[:16]
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
            "source_api": "hep_mirror",
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
    if not keys or not request_data["query"].strip():
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
            rows = parse_toc(read_page(journal, timeout), journal)
            added = []
            for item in rows:
                if mode == "keywords" and not matches_keywords(item, terms):
                    continue
                if item["external_id"] in seen:
                    continue
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
        write_output(Path(args.output), request_data.get("execution_id", ""), items, status, warnings, error)
        return 0 if successful else 1
    except Exception as exc:
        write_output(Path(args.output), request_data.get("execution_id", ""), [], "failed", [], {
            "code": "CRAWLER_ERROR", "message": f"{type(exc).__name__}: {exc}", "retryable": False})
        return 1


if __name__ == "__main__":
    sys.exit(main())
