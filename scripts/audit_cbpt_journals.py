"""Audit every catalogued CBPT journal through the actual crawler code path."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PACKAGE = ROOT / "crawler_packages" / "academic" / "cnki_cbpt"
SPEC = importlib.util.spec_from_file_location("audit_cbpt_crawler", PACKAGE / "crawler.py")
CRAWLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CRAWLER)


def probe(journal: dict, queries: tuple[str, ...], timeout: int) -> dict:
    started = time.monotonic()
    result = {
        "journal_key": journal["journal_key"], "name": journal["name"],
        "url": journal["url"], "source_row": journal["source_row"],
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed", "query": None, "item_count": 0,
        "error": None, "elapsed_seconds": None,
    }
    try:
        from crawler_platform.protocol import load_manifest, validate_item

        manifest = load_manifest(PACKAGE)
        catalog = {journal["journal_key"]: journal}
        for query in queries:
            items, warnings, successful = CRAWLER.collect({
                "query": query, "limit": 3,
                "parameters": {"journal_keys": [journal["journal_key"]],
                               "per_journal_limit": 3, "timeout_seconds": timeout},
            }, catalog)
            result["query"] = query
            if not successful:
                raise RuntimeError("; ".join(warnings) or "crawler returned no successful site")
            for item in items:
                validate_item(manifest, item)
            if items:
                result["status"] = "passed_with_items"
                result["item_count"] = len(items)
                result["sample_title"] = items[0]["title"]
                break
            result["status"] = "passed_no_items"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"[:1000]
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--query", action="append", dest="queries")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--only-failed-from", type=Path)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8 or not 5 <= args.timeout <= 60:
        parser.error("workers must be 1-8 and timeout must be 5-60")
    journals = json.loads((PACKAGE / "journals.json").read_text(encoding="utf-8"))
    failed_keys = None
    if args.only_failed_from is not None:
        failed_keys = {
            row["journal_key"] for line in args.only_failed_from.read_text(encoding="utf-8").splitlines()
            if line.strip() and (row := json.loads(line))["status"] == "failed"
        }
    completed = set()
    if args.resume and args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                completed.add(json.loads(line)["journal_key"])
    remaining = [row for row in journals if row["journal_key"] not in completed
                 and (failed_keys is None or row["journal_key"] in failed_keys)]
    if args.limit is not None:
        remaining = remaining[:args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.resume else "w"
    counts = {"passed_with_items": 0, "passed_no_items": 0, "failed": 0}
    with args.output.open(mode, encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(probe, row, tuple(args.queries or ["人工智能", "研究"]), args.timeout)
                       for row in remaining]
            for index, future in enumerate(as_completed(futures), 1):
                result = future.result()
                counts[result["status"]] += 1
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                handle.flush()
                if index % 25 == 0 or index == len(futures):
                    print(json.dumps({"done": index, "total": len(futures), **counts}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
