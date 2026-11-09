"""Export the latest per-journal capacity result from the append-only audit log."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "journal_catalog" / "audit-capacity-70-2026-10-28.jsonl"
TARGET = ROOT / "journal_catalog" / "journal-capacity-70-2026-10-29.csv"


def reason(row):
    if row["status"] == "reached_70":
        return "confirmed_at_least_70"
    if any(isinstance(warning, dict) and warning.get("code") == "PAGINATION_STALLED"
           for warning in row["warnings"]):
        return "pagination_stalled"
    if row["status"] == "failed":
        return "request_or_parse_failed"
    if row["warnings"]:
        return "interrupted_before_70"
    return "fewer_than_70_for_test_query"


def main():
    latest = {}
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            latest[(row["package_key"], row["journal_key"])] = row
    if len(latest) != 925:
        raise ValueError(f"incomplete audit: expected 925 journals, got {len(latest)}")
    fields = ("package_key", "journal_key", "name", "url", "query", "status", "reason",
              "valid_count", "returned_count", "warnings", "error", "elapsed_seconds", "tested_at_utc")
    with TARGET.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(latest.values(), key=lambda value: (value["package_key"], value["name"])):
            output = {field: row.get(field) for field in fields}
            output["reason"] = reason(row)
            output["warnings"] = json.dumps(row["warnings"], ensure_ascii=False)
            writer.writerow(output)
    print({"file": str(TARGET), "rows": len(latest),
           "status": dict(Counter(row["status"] for row in latest.values())),
           "reason": dict(Counter(reason(row) for row in latest.values()))})


if __name__ == "__main__":
    main()
