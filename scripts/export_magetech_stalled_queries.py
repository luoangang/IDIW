"""Flatten alternate-term and negative-control Magtech probes into one CSV."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "journal_catalog"
TERMS = ROOT / "audit-magetech-stalled-terms-2026-10-29.jsonl"
NEGATIVE = ROOT / "audit-magetech-stalled-negative-2026-10-29.jsonl"
OUTPUT = ROOT / "magetech-stalled-query-diagnosis-2026-10-29.csv"


def read_latest(path):
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            rows[item["journal_key"]] = item
    return rows


def main():
    terms = read_latest(TERMS)
    negative = read_latest(NEGATIVE)
    if len(terms) != 70 or set(terms) != set(negative):
        raise ValueError("the two probe logs must cover the same 70 journals")
    fields = ["journal_key", "name", "url", "page_classification", "same_first_page_across_terms",
              "negative_classification", "negative_count", "negative_same_as_research", "negative_error"]
    for term in ("研究", "技术", "发展"):
        fields.extend([term + suffix for suffix in ("_first_count", "_second_count", "_reported_pages",
                                                   "_reported_records", "_second_reported_page", "_same_page",
                                                   "_error")])
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for key, row in sorted(terms.items(), key=lambda entry: entry[1]["name"]):
            control = negative[key]
            output = {"journal_key": key, "name": row["name"], "url": row["url"],
                      "page_classification": row["classification"],
                      "same_first_page_across_terms": row["same_first_page_across_terms"],
                      "negative_classification": control["classification"],
                      "negative_count": control.get("returned_count"),
                      "negative_same_as_research": control.get("same_as_research_first_page"),
                      "negative_error": control["error"]}
            for term, pages in row["terms"].items():
                first = pages[0]
                second = pages[1] if len(pages) > 1 else {}
                output.update({term + "_first_count": len(first.get("ids", [])),
                               term + "_second_count": len(second.get("ids", [])),
                               term + "_reported_pages": first.get("reported_pages"),
                               term + "_reported_records": first.get("reported_records"),
                               term + "_second_reported_page": second.get("reported_page"),
                               term + "_same_page": bool(first.get("ids")) and first.get("ids") == second.get("ids"),
                               term + "_error": first.get("error") or second.get("error")})
            writer.writerow(output)
    print({"file": str(OUTPUT), "rows": len(terms),
           "pagination": dict(Counter(row["classification"] for row in terms.values())),
           "negative": dict(Counter(row["classification"] for row in negative.values()))})


if __name__ == "__main__":
    main()
