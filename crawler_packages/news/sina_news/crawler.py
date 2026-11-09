from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


API_URL = "https://search.sina.com.cn/api/news"
TAG_RE = re.compile(r"<[^>]*>")


class CrawlerError(Exception):
    def __init__(self, code, message, retryable=False, retry_after_seconds=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


def clean_text(value):
    if value is None:
        return ""
    return " ".join(html.unescape(TAG_RE.sub("", str(value))).split())


def clean_url(value):
    value = html.unescape(str(value or "")).strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    query = urlencode(
        [(key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True)
         if not (key == "from" and item == "pcsearch")],
        doseq=True,
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def parse_datetime(row):
    value = row.get("ctime")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
    text = str(row.get("dataTime") or row.get("time") or "").strip()
    if not text:
        return None
    try:
        # 新浪返回的无时区时间是北京时间。
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return (parsed - timedelta(hours=8)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def iso_utc(value):
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_boundary(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CrawlerError("CONFIG_INVALID", "time_range must include a timezone")
    return parsed.astimezone(timezone.utc)


def in_time_range(value, start, end):
    if value is None:
        return start is None and end is None
    return (start is None or value >= start) and (end is None or value < end)


def convert_item(row):
    if not isinstance(row, dict):
        return None
    external_id = clean_text(row.get("dataid"))
    title = clean_text(row.get("title"))
    url = clean_url(row.get("url"))
    if not external_id or not title or not url:
        return None
    published = parse_datetime(row)
    summary = clean_text(row.get("searchSummary") or row.get("intro")) or None
    author = clean_text(row.get("author")) or None
    publisher = clean_text(row.get("media_show") or row.get("media")) or None
    thumbnail = clean_url(row.get("thumb")) or None
    document_type = clean_text(row.get("docType")) or None
    return {
        "external_id": external_id[:256],
        "title": title[:1000],
        "url": url,
        "summary": summary,
        "author": author[:255] if author else None,
        "publisher": publisher[:255] if publisher else None,
        "published_at": iso_utc(published),
        "thumbnail_url": thumbnail,
        "document_type": document_type[:64] if document_type else None,
        "source_site": "sina_news",
    }


def fetch_page(query, sort, page, page_size, timeout=20):
    url = API_URL + "?" + urlencode({
        "q": query,
        "tp": "news",
        "sort": sort,
        "page": page,
        "size": page_size,
        "from": "search_result",
    })
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 crawler-package-platform/1.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://search.sina.com.cn/",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if exc.code == 429:
            raise CrawlerError(
                "RATE_LIMITED", "Sina News API rate limit exceeded", True,
                int(retry_after) if retry_after and retry_after.isdigit() else None,
            ) from exc
        if 500 <= exc.code < 600:
            raise CrawlerError("NETWORK_ERROR", f"Sina News API returned HTTP {exc.code}", True) from exc
        raise CrawlerError("NETWORK_ERROR", f"Sina News API returned HTTP {exc.code}", False) from exc
    except (URLError, TimeoutError) as exc:
        raise CrawlerError("NETWORK_ERROR", f"Sina News API request failed: {exc}", True) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CrawlerError("PARSE_ERROR", f"Sina News API returned invalid JSON: {exc}", True) from exc

    if not isinstance(payload, dict) or payload.get("code") != 0:
        message = payload.get("message") if isinstance(payload, dict) else "invalid response object"
        raise CrawlerError("PARSE_ERROR", f"Sina News API error: {message}", False)
    data = payload.get("data")
    rows = data.get("list") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise CrawlerError("PARSE_ERROR", "Sina News API response is missing data.list", True)
    return rows


def parse_cursor(cursor, configured_page_size):
    if cursor is None:
        return 1, 0, configured_page_size
    if not isinstance(cursor, dict) or set(cursor) != {"page", "offset", "page_size"}:
        raise CrawlerError("CONFIG_INVALID", "cursor must contain page, offset and page_size")
    page, offset, page_size = cursor["page"], cursor["offset"], cursor["page_size"]
    if (not isinstance(page, int) or page < 1 or not isinstance(offset, int) or offset < 0
            or not isinstance(page_size, int) or not 1 <= page_size <= 50 or offset >= page_size):
        raise CrawlerError("CONFIG_INVALID", "cursor values are invalid")
    return page, offset, page_size


def collect(request_data):
    parameters = request_data.get("parameters", {})
    sort = parameters.get("sort", 0)
    configured_page_size = parameters.get("page_size", 10)
    max_pages = parameters.get("max_pages", 10)
    page, offset, page_size = parse_cursor(request_data.get("cursor"), configured_page_size)
    start = parse_boundary(request_data.get("time_range", {}).get("from"))
    end = parse_boundary(request_data.get("time_range", {}).get("to"))
    limit = request_data["limit"]
    items = []
    warnings = []
    pages_fetched = 0
    has_more = True

    while len(items) < limit and pages_fetched < max_pages:
        rows = fetch_page(request_data["query"], sort, page, page_size)
        pages_fetched += 1
        if offset > len(rows):
            raise CrawlerError("PARSE_ERROR", "cursor offset exceeds the returned page size", False)
        index = offset
        while index < len(rows) and len(items) < limit:
            row = rows[index]
            index += 1
            item = convert_item(row)
            if item is None:
                warnings.append({"code": "ITEM_SKIPPED", "message": "A result lacked dataid, title, or a valid URL"})
                continue
            published = parse_datetime(row)
            if in_time_range(published, start, end):
                items.append(item)

        if index < len(rows):
            offset = index
            has_more = True
            break
        if len(rows) < page_size:
            offset = 0
            has_more = False
            break
        page += 1
        offset = 0
    else:
        has_more = pages_fetched >= max_pages or len(items) >= limit

    next_cursor = {"page": page, "offset": offset, "page_size": page_size} if has_more else None
    if warnings:
        skipped = len(warnings)
        warnings = [{"code": "ITEMS_SKIPPED", "message": f"Skipped {skipped} malformed result(s)"}]
    return items, next_cursor, has_more, warnings


def write_output(output, execution_id, items, status="completed", next_cursor=None,
                 has_more=False, warnings=None, error=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    result = {
        "protocol_version": "1.0",
        "execution_id": execution_id,
        "status": status,
        "item_count": len(items),
        "next_cursor": next_cursor,
        "has_more": has_more,
        "warnings": warnings or [],
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
    output = Path(args.output)
    request_data = {}
    try:
        request_data = json.loads(Path(args.request).read_text(encoding="utf-8"))
        items, next_cursor, has_more, warnings = collect(request_data)
        write_output(output, request_data["execution_id"], items, next_cursor=next_cursor,
                     has_more=has_more, warnings=warnings)
        return 0
    except CrawlerError as exc:
        error = {"code": exc.code, "message": exc.message, "retryable": exc.retryable}
        if exc.retry_after_seconds is not None:
            error["retry_after_seconds"] = exc.retry_after_seconds
        write_output(output, request_data.get("execution_id", ""), [], "failed", error=error)
        return 1
    except Exception as exc:
        write_output(
            output, request_data.get("execution_id", ""), [], "failed",
            error={"code": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}", "retryable": False},
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
