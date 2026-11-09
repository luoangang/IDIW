"""Fetch each public feed once, then evaluate both topics against that snapshot."""
from __future__ import annotations

import argparse
import importlib.util
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "crawler_packages" / "news" / "rss_multi_feed"
spec = importlib.util.spec_from_file_location("rss_probe_crawler", PACKAGE / "crawler.py")
crawler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawler)


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "crawler_platform_runtime" / "probes" / "rss-feedparser" / "results")
    parser.add_argument("--offline", action="store_true", help="reuse previously cached feed responses")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    urls = manifest["parameters_schema"]["properties"]["feed_urls"]["default"]
    cache_path = args.output / "feed-snapshot.json"
    if args.offline:
        snapshot = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        snapshot = {}
        for url in urls:
            started = time.monotonic()
            try:
                parsed = crawler.fetch_feed(url, 25, 5242880)
                snapshot[url] = {"version": parsed.version, "bozo": bool(parsed.get("bozo")),
                                 "feed": dict(parsed.feed), "entries": list(parsed.entries),
                                 "duration_seconds": round(time.monotonic() - started, 2)}
            except crawler.CrawlerError as exc:
                snapshot[url] = {"error": str(exc), "code": exc.code, "retryable": exc.retryable}
        save_json(cache_path, snapshot)

    def cached_fetch(url, timeout, max_bytes):
        cached = snapshot[url]
        if "error" in cached:
            raise crawler.CrawlerError(cached["code"], cached["error"], cached["retryable"])
        return feedparser.FeedParserDict(cached)

    topics = [
        ("all", "RSS snapshot", {"match_mode": "all"}, []),
        ("embodied", "\u5177\u8eab\u667a\u80fd", {
            "extra_keywords": ["humanoid", "robotics", "vision language action"],
            "keyword_groups": [["robot", "AI"]],
        }, ["embodied AI", "embodied intelligence"]),
        ("military", "\u519b\u4e8b\u667a\u80fd\u4f53", {
            "extra_keywords": ["military AI agents", "military artificial intelligence"],
            "keyword_groups": [["AI", "military"], ["AI", "defense"], ["autonomous", "military"], ["agents", "defence"]],
        }, []),
    ]
    summary = {"tested_at": datetime.now(timezone.utc).isoformat(), "feedparser_version": feedparser.__version__,
               "offline": args.offline, "http_requests": 0 if args.offline else len(urls), "feeds": [], "topics": []}
    for url, cached in snapshot.items():
        summary["feeds"].append({"url": url, "entries": len(cached.get("entries", [])),
                                 "format": cached.get("version"), "error": cached.get("error"),
                                 "duration_seconds": cached.get("duration_seconds")})
    report = ["# RSS multi-feed live probe", "", f"Tested at: {summary['tested_at']}",
              f"feedparser: {feedparser.__version__}; HTTP requests: {summary['http_requests']}", "",
              "Each feed was fetched once. Topic results use the same snapshot. No database writes.", ""]
    for slug, query, parameters, aliases in topics:
        directory = args.output / slug
        directory.mkdir(exist_ok=True)
        request = {"protocol_version": "1.0", "package_key": manifest["package_key"],
                   "package_version": manifest["package_version"], "execution_id": str(uuid.uuid4()),
                   "query": query, "aliases": aliases, "limit": 200, "parameters": parameters,
                   "cursor": None, "cursor_version": 0, "time_range": {"from": None, "to": None},
                   "deadline_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
        save_json(directory / "request.json", request)
        items, outcome = crawler.collect(request, cached_fetch)
        crawler.write_output(directory / "output", request["execution_id"], items, outcome)
        terms = [query, *aliases, *parameters.get("extra_keywords", [])]
        examples = [{"title": item["title"], "url": item["url"], "source_site": item["source_site"],
                     "matched_terms": crawler.matching_terms(item, terms, parameters.get("keyword_groups", []))}
                    for item in items[:8]]
        core_matches = None if slug == "all" else sum(bool(crawler.matching_terms(item, [query, *aliases], [])) for item in items)
        row = {"topic": query, "directory": slug, "status": outcome["status"], "count": len(items),
               "core_term_matches": core_matches,
               "stats": [row for row in outcome["warnings"] if row["code"] == "FEED_STATS"], "examples": examples}
        summary["topics"].append(row)
        report.extend([f"## {query}", "", f"Status: {outcome['status']}; items: {len(items)}; core-term matches: {core_matches}", ""])
        for item in examples:
            report.append(f"- [{item['title']}]({item['url']})")
        report.append("")
    report.extend(["## Interpretation", "", "Topic matches are high-recall candidates, not verified relevance judgments.",
                   "Broad terms can match background paragraphs, newsletters, or related-topic mentions; review them before reporting.",
                   "Feed summaries/content are not guaranteed article full text. Rolling feeds do not provide complete history.",
                   "No scheduler, weekly AI report, or installed plugin was changed.", ""])
    save_json(args.output / "summary.json", summary)
    (args.output / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if any(row["status"] == "failed" for row in summary["topics"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
