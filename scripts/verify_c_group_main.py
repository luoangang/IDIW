from __future__ import annotations

import csv
import importlib.util
import sys
import time
import unicodedata
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import build_opener


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"
INPUT = ROOT / "journal_catalog" / "core" / "c-group" / "c-group-main-2026-11-24.csv"
OUTPUT = ROOT / "journal_catalog" / "core" / "c-group" / "c-main-verify-2026-11-24.csv"
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")


def norm(value):
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(value or "")).lower())


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


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def collect(module, key, journal, timeout=12):
    request = {"query": "x", "limit": 80,
               "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                              "per_journal_limit": 80, "timeout_seconds": timeout}}
    items, warnings, _ = module.collect(request, {key: journal})
    return list(items or []), "; ".join(str(value) for value in warnings)[:300]


def magetech_items(module, journal, timeout=12):
    journal_obj = module.journal_from_catalog(journal)
    page = module.fetch_current_issue(build_opener(), journal_obj, timeout)
    items = module.parse_search_result(page, journal_obj) or module.parse_generic_toc(page, journal_obj)
    return list(items or []), ""


def main():
    rows = list(csv.DictReader(INPUT.open(encoding="utf-8-sig")))
    mag = load(ACADEMIC / "magetech_journals" / "crawler.py", "c_mag")
    po = load(ACADEMIC / "paperonce_journals" / "crawler.py", "c_po")
    ct = load(ACADEMIC / "custom_toc_journals" / "crawler.py", "c_ct")
    report = []
    for index, row in enumerate(rows, 1):
        key = f"cm{index:04d}"
        url = row.get("official_url") or row.get("current_url") or ""
        current = row.get("current_url") or url
        journal = {"journal_key": key, "name": row["journal_name"], "url": url, "current_url": current}
        attempts = []
        items, parser_used, error = [], "", ""
        if row["task_batch"] == "MAIN-magetech":
            for attempt in range(2):
                try:
                    items, error = magetech_items(mag, journal, 12)
                except Exception as exc:  # noqa: BLE001
                    items, error = [], f"{type(exc).__name__}: {exc}"
                attempts.append(f"magetech#{attempt + 1}:{len(items)}")
                if items:
                    parser_used = "magetech"
                    break
                time.sleep(2)
        if not items and row["task_batch"] == "MAIN-paperonce":
            probe = dict(journal)
            parts = urlsplit(url or current)
            probe["url"] = f"{parts.scheme}://{parts.netloc}"
            for attempt in range(2):
                try:
                    items, error = collect(po, key, probe, 12)
                except Exception as exc:  # noqa: BLE001
                    items, error = [], f"{type(exc).__name__}: {exc}"
                attempts.append(f"paperonce#{attempt + 1}:{len(items)}")
                if items:
                    parser_used = "paperonce"
                    break
                time.sleep(2)
        if not items:
            try:
                items, error = collect(ct, key, journal, 12)
                attempts.append(f"custom:{len(items)}")
                if items:
                    parser_used = "custom"
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
        matched = title_match(row.get("first_title"), items)
        status = "pass" if items and matched else ("warn" if items else "fail")
        report.append({
            "journal_name": row["journal_name"], "task_batch": row["task_batch"],
            "platform": row.get("platform", ""), "status": status,
            "items": len(items), "expected_items": row.get("agent_items", ""),
            "first_title": (items[0].get("title", "") if items else "")[:160],
            "expected_first_title": row.get("first_title", "")[:160],
            "title_match": "yes" if matched else "no", "verified_parser": parser_used,
            "current_url": current, "official_url": url,
            "attempts": ";".join(attempts), "warnings": error,
        })
        print(f"{index}/{len(rows)} {status} {len(items)} {row['journal_name']} | {row['task_batch']}->{parser_used or '-'} | {report[-1]['first_title'][:50]} | {error[:80]}", flush=True)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report[0].keys()))
        writer.writeheader()
        writer.writerows(report)
    from collections import Counter
    print("saved", OUTPUT)
    print("summary", dict(Counter(row["status"] for row in report)))
    print("parsers", dict(Counter(row["verified_parser"] for row in report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
