from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from itertools import zip_longest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import feedparser


class CrawlerError(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_text(value):
    parser = PlainText()
    parser.feed(str(value or ""))
    parser.close()
    return " ".join("".join(parser.parts).split())


def canonical_url(value, base=""):
    parts = urlsplit(urljoin(base, str(value or "").strip()))
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return ""
    if parts.username or parts.password:
        return ""
    query = sorted(
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(query), ""))


def normalize(value):
    return " ".join(re.sub(r"[\W_]+", " ", unicodedata.normalize("NFKC", value).casefold()).split())


def contains_term(text, term):
    needle = normalize(term)
    if not needle:
        return False
    if needle.isascii():
        return re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", text) is not None
    return needle in text


def matching_terms(item, terms, groups):
    text = normalize(" ".join(str(item.get(key) or "") for key in ("title", "summary", "content")))
    matched = [term for term in terms if contains_term(text, term)]
    matched.extend(" + ".join(group) for group in groups if all(contains_term(text, term) for term in group))
    return matched


def parse_boundary(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    except (ValueError, AttributeError) as exc:
        raise CrawlerError("CONFIG_INVALID", "time values must include a timezone") from exc


def entry_date(entry, key):
    # Bypass feedparser's legacy updated -> published fallback; these are distinct dates.
    parsed = dict.get(entry, key + "_parsed")
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(parsed), timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError):
        return None


def convert_entry(entry, feed, feed_url):
    title = clean_text(entry.get("title"))
    link = entry.get("link")
    url = canonical_url(link, feed.get("link") or feed_url) if link else ""
    if not title or not url:
        return None
    summary = clean_text(entry.get("summary")) or None
    content = "\n".join(clean_text(part.get("value")) for part in entry.get("content", [])).strip() or None
    author = clean_text(entry.get("author")) or None
    publisher = clean_text(feed.get("title")) or None
    language = str(entry.get("language") or feed.get("language") or "").strip() or None
    return {
        "external_id": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "title": title[:1000], "url": url, "summary": summary or content,
        "content": content,
        "content_scope": "feed_content" if content else "feed_summary" if summary else "title_only",
        "publisher": publisher[:255] if publisher else None,
        "author": author[:255] if author else None,
        "published_at": entry_date(entry, "published"), "updated_at": entry_date(entry, "updated"),
        "language": language[:32] if language else None,
        "source_site": urlsplit(url).netloc[:255], "feed_url": feed_url,
    }


def fetch_feed(url, timeout, max_bytes):
    if not canonical_url(url):
        raise CrawlerError("CONFIG_INVALID", "feed URL must be HTTP(S) without embedded credentials")
    request = Request(url, headers={
        "User-Agent": "IDIW-OSINT-RSS/1.0 (+https://github.com/luoangang/IDIW-OSINT)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            headers = {key.lower(): value for key, value in response.headers.items()}
            headers["content-location"] = response.geturl()
    except HTTPError as exc:
        raise CrawlerError("HTTP_ERROR", f"HTTP {exc.code}", exc.code == 429 or exc.code >= 500) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CrawlerError("NETWORK_ERROR", str(exc), True) from exc
    if len(raw) > max_bytes:
        raise CrawlerError("FEED_TOO_LARGE", f"feed exceeds {max_bytes} bytes")
    parsed = feedparser.parse(raw, response_headers=headers)
    if not parsed.get("version", "").startswith(("rss", "atom")):
        raise CrawlerError("PARSE_ERROR", "response is not a supported RSS/Atom feed")
    return parsed


def collect(request_data, fetcher=None):
    fetcher = fetcher or fetch_feed
    manifest = json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))
    parameters = {key: spec["default"] for key, spec in manifest["parameters_schema"]["properties"].items()}
    parameters.update(request_data.get("parameters", {}))
    urls = parameters["feed_urls"]
    if not isinstance(urls, list) or not urls or len(urls) > 32 or any(not isinstance(url, str) or not canonical_url(url) for url in urls):
        raise CrawlerError("CONFIG_INVALID", "feed_urls must contain 1 to 32 HTTP(S) addresses")
    mode = parameters["match_mode"]
    if mode not in {"keywords", "all"}:
        raise CrawlerError("CONFIG_INVALID", "invalid match_mode")
    terms = list(dict.fromkeys([request_data.get("query", ""), *request_data.get("aliases", []), *parameters["extra_keywords"]]))
    terms = [term for term in terms if isinstance(term, str) and normalize(term)]
    groups = parameters["keyword_groups"]
    if mode == "keywords" and not terms and not groups:
        raise CrawlerError("CONFIG_INVALID", "keywords mode requires a query, alias or keyword group")
    limit = request_data.get("limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10000:
        raise CrawlerError("CONFIG_INVALID", "limit must be between 1 and 10000")
    bounds = request_data.get("time_range") or {}
    start, end = parse_boundary(bounds.get("from")), parse_boundary(bounds.get("to"))
    if start is None and parameters["lookback_days"]:
        start = datetime.now(timezone.utc) - timedelta(days=parameters["lookback_days"])
    if start is not None and end is not None and start >= end:
        raise CrawlerError("CONFIG_INVALID", "time_range.from must be before time_range.to")
    deadline = parse_boundary(request_data.get("deadline_at"))
    warnings, batches = [], []
    succeeded, failed, interrupted = 0, 0, False
    retryable_failure = False
    for url in dict.fromkeys(urls):
        timeout = parameters["timeout_seconds"]
        if deadline is not None:
            remaining = (deadline - datetime.now(timezone.utc)).total_seconds() - 3
            if remaining <= 0:
                warnings.append({"code": "DEADLINE_APPROACHING", "message": "stopped before the execution deadline"})
                interrupted = True
                break
            timeout = min(timeout, remaining)
        try:
            parsed = fetcher(url, timeout, parameters["max_feed_bytes"])
        except CrawlerError as exc:
            failed += 1
            retryable_failure |= exc.retryable
            warnings.append({"code": "FEED_FAILED", "message": str(exc)[:1000], "feed_url": url, "reason": exc.code})
            continue
        succeeded += 1
        if parsed.get("bozo"):
            warnings.append({"code": "FEED_PARSE_WARNING", "message": "feed has syntax issues; usable entries are retained", "feed_url": url})
        matched, skipped, unknown_dates = [], 0, 0
        for entry in parsed.entries:
            try:
                item = convert_entry(entry, parsed.feed, url)
            except (ValueError, TypeError, AttributeError):
                item = None
            if item is None:
                skipped += 1
                continue
            dated = parse_boundary(item["published_at"] or item["updated_at"])
            if dated is not None and ((start is not None and dated < start) or (end is not None and dated >= end)):
                continue
            if mode == "keywords" and not matching_terms(item, terms, groups):
                continue
            if dated is None and (start is not None or end is not None):
                unknown_dates += 1
            matched.append(item)
        matched.sort(key=lambda item: item["published_at"] or item["updated_at"] or "", reverse=True)
        retained = matched[:parameters["per_feed_limit"]]
        batches.append(retained)
        warnings.append({"code": "FEED_STATS", "message": "feed parsed", "feed_url": url,
                         "scanned": len(parsed.entries), "matched": len(matched), "retained": len(retained)})
        if len(retained) < len(matched):
            warnings.append({"code": "PER_FEED_LIMIT", "message": "matched entries were truncated", "feed_url": url})
        if skipped:
            warnings.append({"code": "ITEMS_SKIPPED", "message": f"skipped {skipped} entries without a usable title/link", "feed_url": url})
        if unknown_dates:
            warnings.append({"code": "UNKNOWN_DATE", "message": f"retained {unknown_dates} undated matches outside date filtering", "feed_url": url})
    if not succeeded:
        return [], {"status": "failed", "warnings": warnings, "error": {
            "code": "DEADLINE_EXCEEDED" if interrupted else "ALL_FEEDS_FAILED",
            "message": "no feed could be fetched", "retryable": interrupted or retryable_failure,
        }}
    # Interleave sources so the first large feed cannot consume the entire limit.
    unique = {}
    for batch in zip_longest(*batches):
        for item in batch:
            if item is not None:
                unique.setdefault(item["external_id"], item)
    items = list(unique.values())[:limit]
    if len(unique) > limit:
        warnings.append({"code": "ITEM_LIMIT", "message": f"{len(unique) - limit} matches exceeded request.limit"})
    partial = failed or interrupted or any(warning["code"] in {"PER_FEED_LIMIT", "ITEM_LIMIT", "ITEMS_SKIPPED"} for warning in warnings)
    return items, {"status": "partial" if partial else "completed", "warnings": warnings, "error": None}


def write_output(output, execution_id, items, outcome):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
    result = {"protocol_version": "1.0", "execution_id": execution_id,
              "status": outcome["status"], "item_count": len(items), "next_cursor": None,
              "has_more": False, "warnings": outcome["warnings"], "error": outcome["error"]}
    temporary = output / "result.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(output / "result.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request_data = {}
    try:
        request_data = json.loads(Path(args.request).read_text(encoding="utf-8-sig"))
        items, outcome = collect(request_data)
    except Exception as exc:
        items = []
        outcome = {"status": "failed", "warnings": [], "error": {
            "code": exc.code if isinstance(exc, CrawlerError) else "INTERNAL_ERROR",
            "message": str(exc), "retryable": getattr(exc, "retryable", False),
        }}
    write_output(Path(args.output), request_data.get("execution_id", ""), items, outcome)
    return 1 if outcome["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
