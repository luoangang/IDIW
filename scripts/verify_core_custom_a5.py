from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUSTOM = ROOT / "crawler_packages" / "academic" / "custom_toc_journals" / "crawler.py"
QINYUN = ROOT / "crawler_packages" / "academic" / "qinyun_journals" / "crawler.py"
INPUT = ROOT / "journal_catalog" / "core" / "core-a5g6-candidates-2026-11-24.csv"
OUTPUT = ROOT / ".local" / "core" / "probe-verify-a5g6-2026-11-24.csv"
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")


def norm(value):
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(value or "")).lower())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def title_match(expected, items):
    expected_norm = norm(expected)
    if not expected_norm:
        return bool(items)
    for item in items:
        title_norm = norm(item.get("title"))
        if not title_norm:
            continue
        if expected_norm in title_norm or title_norm in expected_norm:
            return True
        if SequenceMatcher(None, expected_norm, title_norm).ratio() >= 0.8:
            return True
    return False


def journal_from_row(row, key):
    journal = {
        "journal_key": key,
        "name": row["journal_name"],
        "url": row["official_url"],
        "current_url": row.get("current_url", ""),
        "link_base": row.get("link_base") or None,
        "article_link_regex": row.get("article_link_regex") or None,
        "relaxed_title_filter": str(row.get("relaxed_title_filter", "")).lower() == "true",
    }
    for field in ("pair_link", "pagination"):
        if row.get(field):
            journal[field] = json.loads(row[field])
        else:
            journal.pop(field, None)
    for field in ("section_start_regex", "section_end_regex", "last_section_regex"):
        if row.get(field):
            journal[field] = row[field]
    if row.get("max_response_bytes"):
        journal["max_response_bytes"] = int(float(row["max_response_bytes"]))
    return journal


def main():
    rows = list(csv.DictReader(INPUT.open(encoding="utf-8-sig")))
    custom = load(CUSTOM, "a5_custom")
    qinyun = load(QINYUN, "a5_qinyun")
    report = []
    for index, row in enumerate(rows, 1):
        key = f"a5{index:04d}"
        module = custom if row["target_package"] == "custom_toc_journals" else qinyun
        journal = journal_from_row(row, key)
        request = {
            "query": "x", "limit": 100,
            "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                           "per_journal_limit": 100, "timeout_seconds": 30},
        }
        items, error = [], ""
        for attempt in range(2):
            try:
                items, warnings, successful = module.collect(request, {key: journal})
                error = "; ".join(str(value) for value in warnings)[:300]
            except Exception as exc:  # noqa: BLE001 - report raw failure
                items, error = [], f"{type(exc).__name__}: {exc}"
            if items:
                break
            if attempt == 0:
                time.sleep(2)
        matched = title_match(row.get("expected_first_title"), items)
        status = "pass" if items and matched else ("warn" if items else "fail")
        report.append({
            "journal_name": row["journal_name"],
            "target_package": row["target_package"],
            "status": status,
            "items": len(items),
            "expected_items": row.get("expected_items", ""),
            "first_title": (items[0].get("title", "") if items else "")[:160],
            "expected_first_title": row.get("expected_first_title", "")[:160],
            "title_match": "yes" if matched else "no",
            "warnings": error,
            "current_url": row.get("current_url", ""),
            "article_link_regex": row.get("article_link_regex", ""),
            "link_base": row.get("link_base", ""),
        })
        print(f"{index}/{len(rows)} {status} {len(items)} {row['journal_name']} | {report[-1]['first_title']} | {error}", flush=True)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report[0].keys()))
        writer.writeheader()
        writer.writerows(report)
    print("saved", OUTPUT)
    print("summary", {status: sum(1 for row in report if row["status"] == status)
                      for status in ("pass", "warn", "fail")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
