"""Probe one search page per candidate, keeping per-site evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crawler_platform.protocol import load_manifest, validate_item
from build_supplier_journal_packages import candidate_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", choices=["qinyun_journals", "rhzh_journals", "sancai_journals"])
    parser.add_argument("--query", default="研究")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--records", type=int, default=1)
    parser.add_argument("--from-status", choices=["passed_with_items", "passed_no_items", "failed"])
    parser.add_argument("--baseline-tag", default="first")
    parser.add_argument("--error-pattern")
    parser.add_argument("--journal-key")
    parser.add_argument("--tag", default="first")
    args = parser.parse_args()
    package = ROOT / "crawler_packages" / "academic" / args.package
    spec = importlib.util.spec_from_file_location(f"{args.package}_audit", package / "crawler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = load_manifest(package)
    rows = candidate_rows(args.package)
    if args.from_status:
        previous = ROOT / "journal_catalog" / f"audit-{args.package}-2026-10-26-{args.baseline_tag}.jsonl"
        if not previous.exists() and args.baseline_tag == "first":
            previous = ROOT / "journal_catalog" / f"audit-{args.package}-2026-10-26.jsonl"
        results = {row["journal_key"]: row for row in (json.loads(line) for line in previous.read_text(encoding="utf-8").splitlines())}
        rows = [row for row in rows if results[row["journal_key"]]["status"] == args.from_status]
        if args.error_pattern:
            import re
            rows = [row for row in rows if re.search(args.error_pattern, results[row["journal_key"]].get("error") or "", re.I)]
    if args.limit:
        rows = rows[:args.limit]
    if args.journal_key:
        rows = [row for row in rows if row["journal_key"] == args.journal_key]

    def probe(row):
        started = time.monotonic()
        request = {"query": args.query, "limit": args.records, "parameters": {"journal_keys": [row["journal_key"]], "timeout_seconds": args.timeout}}
        try:
            items, warnings, success = module.collect(request, {row["journal_key"]: row})
            for item in items:
                validate_item(manifest, item)
            status = "passed_with_items" if items else "passed_no_items" if success else "failed"
            error = "; ".join(warnings)[:500] or None
            first_title = items[0]["title"] if items else None
        except Exception as exc:
            status, error, first_title = "failed", f"{type(exc).__name__}: {exc}"[:500], None
        return {"journal_key": row["journal_key"], "name": row["name"], "url": row["url"], "status": status, "item_count": len(items) if status != "failed" else 0, "first_title": first_title, "error": error, "elapsed_seconds": round(time.monotonic() - started, 2)}

    target = ROOT / "journal_catalog" / f"audit-{args.package}-2026-10-26-{args.tag}.jsonl"
    counts = {"passed_with_items": 0, "passed_no_items": 0, "failed": 0}
    with target.open("w", encoding="utf-8") as handle, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(probe, row) for row in rows]
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            counts[result["status"]] += 1
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
            if index % 25 == 0 or index == len(futures):
                print(json.dumps({"done": index, "total": len(futures), "counts": counts}, ensure_ascii=False), flush=True)
    print(target)


if __name__ == "__main__":
    main()
