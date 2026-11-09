"""Merge live per-journal probes into a reviewable supplier audit."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from build_supplier_journal_packages import candidate_rows


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "journal_catalog"
SOURCES = {
    "qinyun_journals": ("second", "second-confirm", "negative", "negative-retry"),
    "rhzh_journals": ("third", "third-confirm", "third-negative", "third-negative-retry"),
    "sancai_journals": ("first", "confirm", "negative", None),
}
FIELDS = [
    "package", "journal_key", "name", "url", "status", "positive_count",
    "confirmation_count", "confirmation_status", "filter_status", "first_title", "error",
]


def load(package: str, tag: str | None) -> dict[str, dict]:
    if tag is None:
        return {}
    path = CATALOG / f"audit-{package}-2026-10-26-{tag}.jsonl"
    if tag == "first" and not path.exists():
        path = CATALOG / f"audit-{package}-2026-10-26.jsonl"
    return {item["journal_key"]: item for item in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())}


def main() -> None:
    output = []
    for package, tags in SOURCES.items():
        positive, confirmation, negative, negative_retry = (load(package, tag) for tag in tags)
        rows = candidate_rows(package)
        for journal in rows:
            key = journal["journal_key"]
            first = positive[key]
            confirmed = confirmation.get(key, {})
            filter_check = negative_retry.get(key) or negative.get(key, {})
            if first["status"] == "passed_with_items":
                if filter_check.get("status") == "query_ignored":
                    status = "query_ignored"
                elif filter_check.get("status") == "filters_query":
                    status = "verified"
                else:
                    status = "filter_unconfirmed"
            elif first["status"] == "passed_no_items":
                status = "no_results_for_test_query"
            else:
                status = "failed"
            output.append({
                "package": package, "journal_key": key, "name": journal["name"], "url": journal["url"],
                "status": status, "positive_count": first.get("item_count", 1 if first["status"] == "passed_with_items" else 0),
                "confirmation_count": confirmed.get("item_count", ""),
                "confirmation_status": confirmed.get("status", ""),
                "filter_status": filter_check.get("status", ""), "first_title": first.get("first_title") or "",
                "error": first.get("error") or confirmed.get("error") or filter_check.get("error") or "",
            })
    path = CATALOG / "supplier-journal-audit-2026-10-26.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output)
    print(path)
    for package in SOURCES:
        print(package, dict(Counter(row["status"] for row in output if row["package"] == package)))


if __name__ == "__main__":
    main()
