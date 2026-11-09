"""Merge Magtech journal audit passes in source-workbook order."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def rows_by_key(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != len({row["journal_key"] for row in rows}):
        raise ValueError(f"duplicate journal keys in {path}")
    return {row["journal_key"]: row for row in rows}


def error_kind(message: str | None) -> str | None:
    if not message:
        return None
    match = re.search(r"HTTP Error (\d+)", message)
    if match:
        return f"http_{match.group(1)}"
    if "UNSUPPORTED_TEMPLATE" in message:
        return "unsupported_template"
    if "TimeoutError" in message or "timed out" in message:
        return "timeout"
    if "SSL" in message or "certificate" in message:
        return "tls"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--failed-retry", type=Path, required=True)
    parser.add_argument("--no-items-retry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    initial = rows_by_key(args.initial)
    retry_failed = rows_by_key(args.failed_retry)
    retry_empty = rows_by_key(args.no_items_retry)
    keys = {row["journal_key"] for row in catalog}
    if set(initial) != keys or set(retry_failed) & set(retry_empty):
        raise ValueError("audit pass coverage does not match catalog")
    results = []
    for row in catalog:
        key = row["journal_key"]
        first = initial[key]
        second = retry_failed.get(key) or retry_empty.get(key)
        final = second if second and (first["status"] == "failed" or second["status"] != "failed") else first
        results.append({
            "source_row": row["source_row"], "journal_key": key,
            "name": row["name"], "url": row["url"],
            "status": final["status"], "query": final["query"],
            "item_count": final["item_count"], "sample_title": final.get("sample_title"),
            "error_kind": error_kind(final["error"]), "error": final["error"],
            "first_status": first["status"],
            "retry_status": second["status"] if second else None,
            "tested_at": final["tested_at"],
        })
    summary = {
        "total": len(results),
        "status_counts": dict(Counter(row["status"] for row in results)),
        "failure_kinds": dict(Counter(row["error_kind"] for row in results if row["status"] == "failed")),
        "failed_retried": len(retry_failed),
        "no_items_retried": len(retry_empty),
        "recovered_failures": sum(row["first_status"] == "failed" and row["status"] != "failed" for row in results),
        "new_matches_on_broad_query": sum(row["first_status"] == "passed_no_items" and row["status"] == "passed_with_items" for row in results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_name(args.output.stem + "-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
