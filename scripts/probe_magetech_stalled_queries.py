"""Probe alternate terms and first two pages for stalled Magtech journals."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_packages.academic.magetech_journals.crawler import JOURNALS, parse_search_result, post_search

AUDIT = ROOT / "journal_catalog" / "audit-capacity-70-2026-10-28.jsonl"
DEFAULT_OUTPUT = ROOT / "journal_catalog" / "audit-magetech-stalled-terms-2026-10-29.jsonl"
NEGATIVE_OUTPUT = ROOT / "journal_catalog" / "audit-magetech-stalled-negative-2026-10-29.jsonl"
TERMS = ("研究", "技术", "发展")
NEGATIVE_TERM = "zxqv908172nomatch"


def targets():
    latest = {}
    for line in AUDIT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            latest[(row["package_key"], row["journal_key"])] = row
    return [row for row in latest.values() if row["package_key"] == "magetech_journals"
            and any(isinstance(warning, dict) and warning.get("code") == "PAGINATION_STALLED"
                    for warning in row["warnings"])]


def page_info(document, journal):
    items = parse_search_result(document, journal)
    def number(pattern):
        match = re.search(pattern, document)
        return int(match.group(1)) if match else None
    return {
        "ids": [item["external_id"] for item in items],
        "reported_page": number(r"第\s*(\d+)\s*页"),
        "reported_pages": number(r"共\s*(\d+)\s*页"),
        "reported_records": number(r"共\s*(\d+)\s*条记录"),
    }


def probe(row, timeout):
    journal = JOURNALS[row["journal_key"]]
    opener = build_opener()
    started = time.monotonic()
    result = {"journal_key": row["journal_key"], "name": row["name"], "url": row["url"],
              "terms": {}, "classification": None, "error": None,
              "tested_at_utc": datetime.now(timezone.utc).isoformat()}
    for term in TERMS:
        pages = []
        for number in (1, 2):
            try:
                document = post_search(opener, journal, term, number, timeout=timeout)
                pages.append(page_info(document, journal))
            except Exception as exc:
                pages.append({"error": f"{type(exc).__name__}: {exc}"[:300]})
                break
            time.sleep(0.25)
        result["terms"][term] = pages
    observations = []
    for pages in result["terms"].values():
        if len(pages) != 2 or "error" in pages[0] or "error" in pages[1]:
            continue
        first, second = pages
        if first["ids"] and first["ids"] == second["ids"]:
            observations.append("repeated_with_more_pages" if (first["reported_pages"] or 0) > 1 else "repeated_single_page")
        elif set(second["ids"]) - set(first["ids"]):
            observations.append("advanced")
    if "repeated_with_more_pages" in observations:
        result["classification"] = "pagination_stalled_despite_more_pages"
    elif "advanced" in observations:
        result["classification"] = "pagination_advanced_for_alternate_term"
    elif observations and set(observations) == {"repeated_single_page"}:
        result["classification"] = "one_page_for_test_terms"
    else:
        result["classification"] = "inconclusive"
    first_pages = [pages[0] for pages in result["terms"].values() if pages and "ids" in pages[0]]
    result["same_first_page_across_terms"] = len(first_pages) == len(TERMS) and all(
        page["ids"] == first_pages[0]["ids"] for page in first_pages[1:])
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def negative_probe(row, timeout, reference):
    journal = JOURNALS[row["journal_key"]]
    result = {"journal_key": row["journal_key"], "name": row["name"], "url": row["url"],
              "term": NEGATIVE_TERM, "classification": "inconclusive", "error": None,
              "tested_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        document = post_search(build_opener(), journal, NEGATIVE_TERM, 1, timeout=timeout)
        info = page_info(document, journal)
        baseline = reference.get(row["journal_key"], {}).get("terms", {}).get("研究", [{}])[0].get("ids", [])
        result.update({"returned_count": len(info["ids"]), "reported_records": info["reported_records"],
                       "same_as_research_first_page": bool(baseline) and baseline == info["ids"]})
        if result["same_as_research_first_page"]:
            result["classification"] = "negative_term_ignored"
        elif not info["ids"]:
            result["classification"] = "negative_term_empty"
        elif baseline:
            result["classification"] = "negative_term_different_results"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--negative-control", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or not 5 <= args.timeout <= 60:
        parser.error("workers must be 1..4 and timeout 5..60")
    rows = targets()
    reference = {}
    if args.negative_control:
        for line in DEFAULT_OUTPUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                saved = json.loads(line)
                reference[saved["journal_key"]] = saved
        if args.output == DEFAULT_OUTPUT:
            args.output = NEGATIVE_OUTPUT
    if args.limit:
        rows = rows[:args.limit]
    done = set()
    if args.output.exists():
        done = {json.loads(line)["journal_key"] for line in args.output.read_text(encoding="utf-8").splitlines() if line.strip()}
    rows = [row for row in rows if row["journal_key"] not in done]
    print(json.dumps({"remaining": len(rows), "previously_tested": len(done)}, ensure_ascii=False), flush=True)
    counts = {}
    with args.output.open("a", encoding="utf-8") as handle, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(negative_probe, row, args.timeout, reference) if args.negative_control
                   else pool.submit(probe, row, args.timeout) for row in rows]
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            counts[result["classification"]] = counts.get(result["classification"], 0) + 1
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
            if index % 10 == 0 or index == len(futures):
                print(json.dumps({"done": index, "total": len(futures), "counts": counts}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
