from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (compatible; JournalMetadataCollector/1.0)"
MAX_RESPONSE = 3_000_000
TAG = re.compile(r"<[^>]+>")
NOISE_TITLE = re.compile(
    r"^(?:\d{4}年)?(?:第?\d+期)?(?:封面|封二|封三|封底|目录|目次|封面和目录|封面、目录)"
    r"|(?:封面|封二|封三|封底|目录|目次|投稿须知|征稿启事|稿约|编委会|编辑委员会|理事会|卷首语|编者按|序言|前言|专栏|专题)$",
    re.I,
)


def get_json(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        encoding = (response.headers.get("Content-Encoding") or "").lower()
    if raw.startswith(b"\x1f\x8b") or "gzip" in encoding:
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("status") != 0:
        raise ValueError(f"Founder API rejected request: {data.get('message') if isinstance(data, dict) else data}")
    return data.get("data")


def read_current_issue(journal, timeout):
    base = journal["base_url"].rstrip("/")
    site_id = journal["site_id"]
    publication_index_id = journal.get("publication_index_id")
    if not publication_index_id:
        detail = get_json(f"{base}/rc-pub/front/front-publication/detail/getDetailBySiteId?siteId={site_id}", timeout) or {}
        publication_index_id = detail.get("id")
    if not publication_index_id:
        raise ValueError("publicationIndexId not found")
    periods = get_json(
        f"{base}/rc-pub/front/front-period/getFirstTwoPeriods?publicationIndexId={publication_index_id}", timeout
    ) or []
    if not periods:
        raise ValueError("no current period")
    period = periods[0]
    articles = get_json(
        f"{base}/rc-pub/front/front-article/getArticlesByPeriodicalId/{period['id']}?siteId={site_id}", timeout
    ) or []
    return period, articles


def clean(value):
    text = html.unescape(TAG.sub("", str(value or "")))
    return " ".join(text.replace("\xa0", " ").split())


def normalize(record, journal, period):
    if not isinstance(record, dict):
        return None
    external_id = str(record.get("id") or record.get("resNo") or "").strip()
    title = clean(record.get("resName") or record.get("enResName"))
    if not external_id or not title or NOISE_TITLE.search(title):
        return None
    doi = clean(record.get("doi"))
    base = journal["base_url"].rstrip("/")
    issue = clean(f"{period.get('year') or ''}年第{period.get('issue') or ''}期") or None
    first = clean(record.get("firstPageNum"))
    last = clean(record.get("lastPageNum"))
    pages = f"{first}-{last}" if first and last and first != last else (first or last or None)
    return {
        "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
        "journal_url": journal["url"], "external_id": external_id[:128],
        "title": title[:1000],
        "url": f"https://doi.org/{doi}" if doi else f"{base}/#/article/{external_id}",
        "authors": clean(record.get("authors") or record.get("enAuthors")) or None,
        "abstract": clean(record.get("summary") or record.get("enSummary")) or None,
        "doi": doi[:255] or None,
        "year": int(record["year"]) if str(record.get("year") or "").isdigit() else None,
        "issue": issue[:64] if issue else None,
        "pages": pages[:64] if pages else None,
        "source_api": "founder",
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
    if not keys or not request_data["query"].strip():
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
        seen = set()
        try:
            period, articles = read_current_issue(journal, timeout)
            for record in articles:
                item = normalize(record, journal, period)
                if mode == "keywords" and item and not matches_keywords(item, terms):
                    continue
                if item and item["external_id"] not in seen:
                    seen.add(item["external_id"])
                    items.append(item)
                    if len(seen) >= per_journal or len(items) >= limit:
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
