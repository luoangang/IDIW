from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (compatible; JournalMetadataCollector/1.0)"
MAX_RESPONSE = 3_000_000
DIRECTORY_TITLE = re.compile(r"(?:目录|封面|封底|征稿|启事|稿约)\s*$")
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.I)


def clean(value):
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return " ".join(text.split())


def read_feed(journal, timeout):
    base = journal.get("rss_url") or journal["url"].rstrip("/") + "/oa/rss.aspx"
    request = Request(
        base,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
    return raw


def parse_feed(raw, journal):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"invalid RSS XML: {exc}") from exc
    channel = root.find("channel")
    if channel is None:
        raise ValueError("RSS lacks channel")
    channel_year = clean(channel.findtext("year"))
    channel_month = clean(channel.findtext("month"))
    base = journal["url"].rstrip("/") + "/"
    seen = set()
    items = []
    for node in channel.findall("item"):
        title = clean(node.findtext("title"))
        link = clean(node.findtext("link"))
        if not title or not link or DIRECTORY_TITLE.search(title):
            continue
        article_url = urljoin(base, link)
        identifier = re.search(r"[?&]id=([^&#]+)", article_url, re.I)
        external_id = html.unescape(identifier.group(1)) if identifier else hashlib.sha1(article_url.encode("utf-8")).hexdigest()[:16]
        if external_id in seen:
            continue
        seen.add(external_id)
        issue = clean(node.findtext("issue"))
        pub_date = clean(node.findtext("pubDate"))
        year_match = re.search(r"(19\d{2}|20\d{2})", issue or pub_date or channel_year)
        doi_match = DOI_PATTERN.search(clean(node.findtext("description")))
        abstract = clean(node.findtext("description"))
        if not issue and (channel_year or channel_month):
            issue = f"{channel_year}年{channel_month}月" if channel_year else channel_month
        items.append({
            "journal_key": journal["journal_key"],
            "journal_name": journal["name"][:255],
            "journal_url": journal["url"],
            "external_id": external_id[:128],
            "title": title[:1000],
            "url": article_url,
            "authors": clean(node.findtext("author")) or None,
            "abstract": abstract[:8000] or None,
            "doi": doi_match.group(0).rstrip(".,;，；")[:255] if doi_match else None,
            "year": int(year_match.group(0)) if year_match else None,
            "issue": issue[:64] or None,
            "source_api": "oa_rss",
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
    items, warnings, successful = [], [], 0
    for key in keys:
        if len(items) >= limit:
            break
        journal = journals.get(key)
        if not journal:
            warnings.append(f"Unknown journal key: {key}")
            continue
        try:
            rows = parse_feed(read_feed(journal, timeout), journal)
            added = 0
            for item in rows:
                if mode == "keywords" and not matches_keywords(item, terms):
                    continue
                items.append(item)
                added += 1
                if added >= per_journal or len(items) >= limit:
                    break
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
