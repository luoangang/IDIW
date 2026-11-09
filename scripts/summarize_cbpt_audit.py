"""Merge first-pass and retry journal audits without losing either result."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def read_jsonl(path: Path) -> dict[str, dict]:
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
    if "TimeoutError" in message or "timed out" in message:
        return "timeout"
    if "certificate verify failed" in message:
        return "tls_certificate"
    if "site did not return a CBPT search page" in message:
        return "template_mismatch"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--retry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    initial = read_jsonl(args.initial)
    retry = read_jsonl(args.retry)
    catalog_keys = {row["journal_key"] for row in catalog}
    if set(initial) != catalog_keys or not set(retry).issubset(catalog_keys):
        raise ValueError("audit results do not match the package catalog")
    results = []
    for journal in catalog:
        key = journal["journal_key"]
        first = initial[key]
        second = retry.get(key)
        final = second or first
        results.append({
            "source_row": journal["source_row"], "journal_key": key,
            "name": journal["name"], "url": journal["url"],
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
        "retried": len(retry),
        "recovered_on_retry": sum(row["first_status"] == "failed" and row["status"] != "failed" for row in results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_name(args.output.stem + "-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
