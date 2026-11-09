"""Live smoke test for 20 public US grant numbers (requires USPTO access)."""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

from crawler_packages.patents.uspto_number_lookup.crawler import run


PATENTS = (
    "11748653", "11914366", "11968088", "9983582", "12210592",
    "10850344", "10710250", "11971914", "12174954", "12067476",
    "9931956", "10162010", "9991724", "10547184", "9172256",
    "9527400", "10374444", "9787108", "9377839", "12202142",
)


def main() -> None:
    version = json.loads((Path(__file__).resolve().parents[1] / "crawler_packages" /
                          "patents" / "uspto_number_lookup" / "manifest.json").read_text(
                              encoding="utf-8"))["package_version"]
    rows = []
    for offset in range(0, len(PATENTS), 5):
        batch = PATENTS[offset:offset + 5]
        request = {
            "protocol_version": "1.0",
            "execution_id": str(uuid.uuid4()),
            "package_key": "uspto_number_lookup",
            "package_version": version,
            "query": "; ".join(batch),
            "aliases": [],
            "limit": len(batch),
            "parameters": {},
            "cursor": None,
            "time_range": {"from": None, "to": None},
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            run(request, output)
            result = json.loads((output / "result.json").read_text(encoding="utf-8"))
            items = [json.loads(line) for line in (output / "items.jsonl").read_text(
                encoding="utf-8").splitlines() if line.strip()]
        by_number = {item["patent_number"]: item for item in items}
        for number in batch:
            item = by_number.get(number)
            row = {
                "patent_number": number,
                "found": item is not None,
                "document_id": item["external_id"] if item else None,
                "title": item["title"] if item else None,
                "summary": bool(item and item["summary"]),
                "applicants": bool(item and item["applicants"]),
                "assignees": bool(item and item["assignees"]),
                "application_number": bool(item and item["application_number"]),
                "application_date": bool(item and item["application_date"]),
                "grant_date": bool(item and item["grant_date"]),
            }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        print(json.dumps({
            "batch": offset // 5 + 1,
            "status": result["status"],
            "error": result["error"],
            "warnings": result["warnings"],
        }, ensure_ascii=False), flush=True)
    print(json.dumps({"total": len(rows), "found": sum(row["found"] for row in rows)},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
