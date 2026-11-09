"""Verify that candidate search endpoints do not ignore the supplied keyword."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from build_supplier_journal_packages import candidate_rows

ROOT = Path(__file__).resolve().parents[1]
IMPOSSIBLE_QUERY = "zxqv908172nomatch"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", choices=["qinyun_journals", "rhzh_journals", "sancai_journals"])
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--retry-inconclusive", action="store_true")
    parser.add_argument("--audit-tag", default="second")
    args = parser.parse_args()
    package = ROOT / "crawler_packages" / "academic" / args.package
    spec = importlib.util.spec_from_file_location(f"{args.package}_negative", package / "crawler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    catalog = {row["journal_key"]: row for row in candidate_rows(args.package)}
    suffix = args.audit_tag if args.package != "sancai_journals" else ""
    audit = ROOT / "journal_catalog" / (f"audit-{args.package}-2026-10-26-{suffix}.jsonl" if suffix else f"audit-{args.package}-2026-10-26.jsonl")
    candidates = [json.loads(line)["journal_key"] for line in audit.read_text(encoding="utf-8").splitlines() if json.loads(line)["status"] == "passed_with_items"]
    if args.retry_inconclusive:
        previous = ROOT / "journal_catalog" / f"audit-{args.package}-2026-10-26-{args.audit_tag}-negative.jsonl"
        if not previous.exists() and args.audit_tag == "second":
            previous = ROOT / "journal_catalog" / f"audit-{args.package}-2026-10-26-negative.jsonl"
        retry_keys = {json.loads(line)["journal_key"] for line in previous.read_text(encoding="utf-8").splitlines() if json.loads(line)["status"] == "inconclusive"}
        candidates = [key for key in candidates if key in retry_keys]

    def check(key):
        request = {"query": IMPOSSIBLE_QUERY, "limit": 1, "parameters": {"journal_keys": [key], "timeout_seconds": args.timeout}}
        try:
            items, warnings, success = module.collect(request, {key: catalog[key]})
            status = "query_ignored" if items else "filters_query" if success else "inconclusive"
            return {"journal_key": key, "name": catalog[key]["name"], "status": status, "error": "; ".join(warnings)[:500] or None}
        except Exception as exc:
            return {"journal_key": key, "name": catalog[key]["name"], "status": "inconclusive", "error": f"{type(exc).__name__}: {exc}"[:500]}

    label = "negative-retry" if args.retry_inconclusive else "negative"
    if args.audit_tag != "second":
        label = f"{args.audit_tag}-{label}"
    output = ROOT / "journal_catalog" / f"audit-{args.package}-2026-10-26-{label}.jsonl"
    counts = {"filters_query": 0, "query_ignored": 0, "inconclusive": 0}
    with output.open("w", encoding="utf-8") as handle, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(check, key) for key in candidates]
        for index, future in enumerate(as_completed(futures), 1):
            row = future.result()
            counts[row["status"]] += 1
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            if index % 25 == 0 or index == len(futures):
                print(json.dumps({"done": index, "total": len(futures), "counts": counts}, ensure_ascii=True), flush=True)
    print(output)


if __name__ == "__main__":
    main()
