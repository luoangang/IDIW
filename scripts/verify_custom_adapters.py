from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUSTOM = ROOT / "crawler_packages" / "academic" / "custom_toc_journals"
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")


def norm(value):
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(value or "")).lower())


def load_custom():
    path = CUSTOM / "crawler.py"
    spec = importlib.util.spec_from_file_location("verify_custom", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_custom"] = module
    spec.loader.exec_module(module)
    return module


def title_match(expected, items):
    expected_norm = norm(expected)
    if not expected_norm:
        return bool(items)
    for item in items[:5]:
        title_norm = norm(item.get("title"))
        if not title_norm:
            continue
        if expected_norm in title_norm or title_norm in expected_norm:
            return True
        if SequenceMatcher(None, expected_norm, title_norm).ratio() >= 0.8:
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "journal_catalog" / "core" / "core-a4-candidates-2026-11-24.csv"))
    parser.add_argument("--output", default=str(ROOT / ".local" / "core" / "probe-verify-custom-a4-2026-11-24.csv"))
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.input).open(encoding="utf-8-sig")))
    module = load_custom()
    report = []
    for index, row in enumerate(rows, 1):
        journal = {
            "journal_key": f"a4p{index:04d}",
            "name": row["journal_name"],
            "url": row.get("official_url") or row.get("current_url"),
            "current_url": row.get("current_url"),
            "article_link_regex": row.get("article_link_regex"),
            "link_base": row.get("link_base"),
            "relaxed_title_filter": True,
        }
        items, error, attempt = [], "", 0
        for attempt in range(args.retries + 1):
            try:
                page = module.read_page(journal, 25)
                items = module.parse_toc(page, journal) or []
            except Exception as exc:  # noqa: BLE001 - report raw failure
                items, error = [], f"{type(exc).__name__}: {exc}"
            matched = title_match(row.get("first_title"), items)
            if items and matched:
                break
        matched = title_match(row.get("first_title"), items)
        status = "pass" if items and matched else ("warn" if items else "fail")
        report.append({
            "journal_name": row["journal_name"],
            "platform": row.get("platform", ""),
            "status": status,
            "items": len(items),
            "first_title": items[0].get("title", "")[:160] if items else "",
            "expected_title": row.get("first_title", "")[:160],
            "title_match": "yes" if matched else "no",
            "attempt": attempt + 1,
            "warnings": error[:300],
            "current_url": row.get("current_url", ""),
            "article_link_regex": row.get("article_link_regex", ""),
            "link_base": row.get("link_base", ""),
            "data_source": row.get("data_source", ""),
        })
        print(f"{index}/{len(rows)} {status} {len(items)} {row['journal_name']}", flush=True)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report[0].keys()))
        writer.writeheader()
        writer.writerows(report)
    counts = Counter(row["status"] for row in report)
    print("summary", dict(counts), flush=True)
    print("saved", out_path, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
