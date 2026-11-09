"""One-page public search audit for every supplier-labeled Magtech journal."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import build_opener


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PACKAGE = ROOT / "crawler_packages" / "academic" / "magetech_journals"
SPEC = importlib.util.spec_from_file_location("audit_magetech_crawler", PACKAGE / "crawler.py")
CRAWLER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CRAWLER
SPEC.loader.exec_module(CRAWLER)


def probe(row: dict, timeout: int, query: str) -> dict:
    from crawler_platform.protocol import load_manifest, validate_item

    started = time.monotonic()
    result = {
        "source_row": row["source_row"], "journal_key": row["journal_key"],
        "name": row["name"], "url": row["url"], "query": query,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed", "item_count": 0, "error": None,
    }
    try:
        journal = CRAWLER.journal_from_catalog(row)
        document = CRAWLER.post_search(build_opener(), journal, query, 1, timeout=timeout)
        items = CRAWLER.parse_search_result(document, journal)
        manifest = load_manifest(PACKAGE)
        for item in items[:3]:
            validate_item(manifest, item)
        result["status"] = "passed_with_items" if items else "passed_no_items"
        result["item_count"] = len(items)
        if items:
            result["sample_title"] = items[0]["title"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:1000]
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--query", default="人工智能")
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--only-failed-from", type=Path)
    selection.add_argument("--only-no-items-from", type=Path)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8 or not 5 <= args.timeout <= 60:
        parser.error("workers must be 1-8 and timeout must be 5-60")
    rows = json.loads((PACKAGE / "journals.json").read_text(encoding="utf-8"))
    if args.only_failed_from or args.only_no_items_from:
        source = args.only_failed_from or args.only_no_items_from
        wanted_status = "failed" if args.only_failed_from else "passed_no_items"
        selected_keys = {
            row["journal_key"] for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip() and (row := json.loads(line))["status"] == wanted_status
        }
        rows = [row for row in rows if row["journal_key"] in selected_keys]
    completed = set()
    if args.resume and args.output.exists():
        completed = {
            json.loads(line)["journal_key"]
            for line in args.output.read_text(encoding="utf-8").splitlines() if line.strip()
        }
    rows = [row for row in rows if row["journal_key"] not in completed]
    if args.limit:
        rows = rows[:args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts = {"passed_with_items": 0, "passed_no_items": 0, "failed": 0}
    with args.output.open("a" if args.resume else "w", encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(probe, row, args.timeout, args.query) for row in rows]
            for index, future in enumerate(as_completed(futures), 1):
                result = future.result()
                counts[result["status"]] += 1
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                handle.flush()
                if index % 25 == 0 or index == len(rows):
                    print(json.dumps({"done": index, "total": len(rows), **counts}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
