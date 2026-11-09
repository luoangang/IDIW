from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (compatible; JournalMetadataCollector/1.0)"
MAX_RESPONSE = 3_000_000
API_SITES = {
    "7371a30d9aa7945b": "https://xbbjb.hfnu.edu.cn",
    "1d43330d46323f18": "http://journal.ahnu.edu.cn",
}


def search_page(journal, query, page, timeout):
    base = API_SITES.get(journal["journal_key"])
    if not base:
        raise ValueError("UNSUPPORTED_TEMPLATE: no verified Samson ArticleSearch API")
    payload = {
        "PageIndex": page, "PageSize": 10,
        "SearchKey": [{"Type": "Title", "Key": query}],
        "ColunmIds": [], "FieldIds": [],
    }
    request = Request(
        f"{base}/api/api/Web/ArticleSearch",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/json; charset=utf-8", "Referer": base + "/"},
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("Data"), list):
        raise ValueError("UNSUPPORTED_TEMPLATE: Samson response lacks Data list")
    if data.get("IsSuccess") is False:
        raise ValueError(f"search rejected: {data.get('Message')}")
    return data["Data"]


def clean(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())


def normalize(record, journal):
    if not isinstance(record, dict):
        return None
    title = clean(record.get("Title") or record.get("TitleE"))
    article_id = str(record.get("ArticleID") or "").strip()
    if not title or not article_id:
        return None
    base = API_SITES[journal["journal_key"]]
    doi = clean(record.get("DOI"))
    date = str(record.get("PublishDate") or record.get("Year") or "")[:4]
    return {
        "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
        "journal_url": journal["url"], "external_id": article_id[:128],
        "title": title[:1000], "url": f"{base}/#/digest?ArticleID={quote(article_id)}",
        "authors": clean(record.get("AuthorsList") or record.get("AuthorsListE")) or None,
        "abstract": clean(record.get("Abstract_Chinese") or record.get("Abstract_English")) or None,
        "doi": doi[:255] or None, "year": int(date) if date.isdigit() else None,
    }


def collect(request_data, journals):
    params = request_data.get("parameters") or {}
    keys = params.get("journal_keys", list(API_SITES))
    query = request_data["query"].strip()
    if not keys or not query:
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
        seen = set()
        try:
            for page in range(1, min(100, per_journal) + 1):
                rows = search_page(journal, query, page, timeout)
                if not rows:
                    break
                previous_count = len(seen)
                for record in rows:
                    item = normalize(record, journal)
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
