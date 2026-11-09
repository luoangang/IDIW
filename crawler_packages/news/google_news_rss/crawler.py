from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


def plain_text(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def query_terms(request_data):
    query, aliases = request_data.get("query"), request_data.get("aliases", [])
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
        raise ValueError("query must be 1-1000 characters")
    if not isinstance(aliases, list) or len(aliases) > 30:
        raise ValueError("aliases must contain at most 30 phrases")
    terms, seen = [], set()
    for index, value in enumerate([query, *aliases]):
        if not isinstance(value, str) or len(value.strip()) > (1000 if index == 0 else 100):
            raise ValueError("invalid query or alias")
        term = " ".join(unicodedata.normalize("NFKC", value).split())
        key = term.casefold()
        if term and key not in seen:
            terms.append(term)
            seen.add(key)
    return terms


def fetch_feed(term, config, timeout):
    language, country = config.get("language", "zh-CN"), config.get("country", "CN")
    query = urlencode({"q": term, "hl": language, "gl": country,
                       "ceid": f"{country}:{language.split('-')[0]}"})
    request = Request("https://news.google.com/rss/search?" + query, headers={
        "User-Agent": "Mozilla/5.0 crawler-package-platform/1.0", "Accept-Language": language,
    })
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("RSS response exceeds 5 MiB")
    root = ElementTree.fromstring(raw)
    if root.find("./channel") is None:
        raise ValueError("response is not an RSS feed")
    return root


def parse_items(root, config):
    items = []
    for node in root.findall("./channel/item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        guid = (node.findtext("guid") or link).strip()
        if not title or not link or not guid:
            continue
        source = node.find("source")
        published_at = None
        if node.findtext("pubDate"):
            try:
                published = parsedate_to_datetime(node.findtext("pubDate"))
                if published.tzinfo is not None:
                    published_at = published.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except (ValueError, TypeError, OverflowError):
                pass
        items.append({
            "external_id": guid[:1000], "title": title[:1000], "url": link,
            "summary": plain_text(node.findtext("description")) or None,
            "publisher": (source.text or "").strip()[:255] or None if source is not None else None,
            "published_at": published_at, "language": config.get("language", "zh-CN"),
            "country": config.get("country", "CN"), "source_site": "google_news_rss",
        })
    return items


def merge_batches(batches, limit):
    items, seen, seen_urls = [], set(), set()
    # Interleave searches so a full primary feed does not consume the whole limit.
    pending = [iter(batch) for batch in batches]
    while pending:
        remaining = []
        for iterator in pending:
            for item in iterator:
                if item["external_id"] in seen or item["url"] in seen_urls:
                    continue
                seen.add(item["external_id"])
                seen_urls.add(item["url"])
                items.append(item)
                if len(items) >= limit:
                    return items
                remaining.append(iterator)
                break
        pending = remaining
    return items


def collect(request_data, fetcher=None):
    fetcher = fetcher or fetch_feed
    terms = query_terms(request_data)
    limit = request_data.get("limit")
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("limit must be 1-10000")
    config = request_data.get("parameters", {})
    if (not isinstance(config, dict) or config.get("language", "zh-CN") not in ("zh-CN", "en-US")
            or config.get("country", "CN") not in ("CN", "US", "GB")):
        raise ValueError("invalid language/country parameters")
    deadline = request_data.get("deadline_at")
    if deadline:
        deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            raise ValueError("deadline_at must include timezone")
    warnings, batches = [], []
    succeeded = 0
    for index, term in enumerate(terms):
        timeout = 20
        if deadline is not None:
            remaining = (deadline - datetime.now(timezone.utc)).total_seconds() - 3
            if remaining <= 0:
                warnings.append({"code": "DEADLINE_APPROACHING", "message": f"未请求剩余 {len(terms)-index} 个检索词：接近执行截止时间"})
                break
            timeout = min(timeout, remaining)
        print(f"[google_news_rss] search {index+1}/{len(terms)}: {term}", file=sys.stderr, flush=True)
        try:
            batch = parse_items(fetcher(term, config, timeout), config)
            succeeded += 1
            batches.append(batch)
            print(f"[google_news_rss] fetched {len(batch)}: {term}", file=sys.stderr, flush=True)
        except Exception as exc:
            warnings.append({"code": "QUERY_FAILED", "message": f"{term}: {type(exc).__name__}: {exc}"[:1000], "query": term})
            print(f"[google_news_rss] failed: {term}: {exc}", file=sys.stderr, flush=True)
    items = merge_batches(batches, limit)
    print(f"[google_news_rss] searches succeeded={succeeded}/{len(terms)}, unique items={len(items)}, limit={limit}", file=sys.stderr, flush=True)
    error = None if succeeded else {"code": "NETWORK_OR_PARSE_ERROR", "message": ("no query could be fetched: " + warnings[0]["message"])[:1000], "retryable": True}
    status = "failed" if not succeeded else "partial" if warnings else "completed"
    return {"items": items, "status": status, "warnings": warnings, "error": error}


def write_output(output, execution_id, items, status="completed", error=None, warnings=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    result = {"protocol_version":"1.0","execution_id":execution_id,"status":status,"item_count":len(items),"next_cursor":None,"has_more":False,"warnings":warnings or [],"error":error}
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
        result = collect(request_data)
        write_output(output, request_data["execution_id"], result["items"], result["status"], result["error"], result["warnings"])
        return 1 if result["status"] == "failed" else 0
    except Exception as exc:
        write_output(output, request_data.get("execution_id", ""), [], "failed", {"code":"CONFIG_INVALID","message":f"{type(exc).__name__}: {exc}","retryable":False})
        return 1


if __name__ == "__main__":
    sys.exit(main())
