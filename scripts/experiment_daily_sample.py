from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"
DATE = "2026-11-24"
OUT_DIR = ROOT / "journal_catalog" / "core"
MODES = {
    "cnki_cbpt": "standard", "custom_toc_journals": "standard", "qinyun_journals": "standard",
    "rhzh_journals": "standard", "founder_journals": "standard", "paperonce_journals": "standard",
    "oa_rss_journals": "standard", "vsb_journals": "standard", "hep_mirror_journals": "standard",
    "sancai_journals": "standard", "magetech_journals": "magetech",
    "supplement_journals": "supplement", "flagship_journals": "flagship",
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def catalog(package, module):
    if package == "flagship_journals":
        return {key: {"journal_key": key, "name": value[0]} for key, value in module.JOURNALS.items()}
    path = ACADEMIC / package / "journals.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row.get("journal_key"): row for row in rows if row.get("name")}


def pick(rows, seed):
    keys = sorted(rows)
    rng = random.Random(seed)
    return rng.sample(keys, min(5, len(keys)))


def text(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)[:500]
    return str(value or "")


def flatten(item):
    return {
        "title": text(item.get("title"))[:300],
        "authors": text(item.get("authors"))[:300],
        "abstract_len": len(text(item.get("abstract"))) if item.get("abstract") else 0,
        "doi": text(item.get("doi"))[:150],
        "year": text(item.get("year"))[:20],
        "issue": text(item.get("issue"))[:80],
        "url": text(item.get("url"))[:400],
        "pdf_url": text(item.get("pdf_url"))[:400],
        "published_at": text(item.get("published_at") or item.get("published") or item.get("date"))[:40],
    }


def run_standard(module, package, rows, keys):
    journals = {key: rows[key] for key in keys}
    request = {"query": "x", "limit": 15,
               "parameters": {"journal_keys": keys, "collect_mode": "latest_issue",
                              "per_journal_limit": 3, "timeout_seconds": 12}}
    items, warnings, _ = module.collect(request, journals)
    return items, [text(value) for value in warnings]


def run_magetech(module, rows, keys):
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    request = {"query": "x", "limit": 15, "deadline_at": deadline,
               "parameters": {"journal_keys": keys, "collect_mode": "latest_issue",
                              "per_journal_limit": 3, "timeout_seconds": 12}}
    items, warnings, _ = module.collect(request)
    return items, [text(value.get("message") if isinstance(value, dict) else value) for value in warnings]


def run_supplement(module, rows, keys):
    request = {"query": "x", "limit": 15,
               "parameters": {"journal_keys": keys, "collect_mode": "latest_issue",
                              "per_journal_limit": 3, "lookback_days": 7, "timeout_seconds": 12}}
    items, warnings, _ = module.collect(request)
    return items, [text(value.get("message") if isinstance(value, dict) else value) for value in warnings]


def run_flagship(module, rows, keys):
    request = {"query": "artificial intelligence", "limit": 15,
               "parameters": {"journal_keys": keys, "per_journal_limit": 3,
                              "lookback_days": 7, "timeout_seconds": 12}}
    items, warnings, _ = module.collect(request)
    return items, [text(value) for value in warnings]


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--packages", required=True, help="逗号分隔的包名")
    cli.add_argument("--output", required=True)
    args = cli.parse_args()
    packages = [value.strip() for value in args.packages.split(",") if value.strip()]

    journal_rows, item_rows = [], []
    for package in packages:
        mode = MODES[package]
        module = load(ACADEMIC / package / "crawler.py", f"daily_{package}")
        rows = catalog(package, module)
        keys = pick(rows, 20261124 + sum(ord(ch) for ch in package))
        try:
            if mode == "magetech":
                items, warnings = run_magetech(module, rows, keys)
            elif mode == "supplement":
                items, warnings = run_supplement(module, rows, keys)
            elif mode == "flagship":
                items, warnings = run_flagship(module, rows, keys)
            else:
                items, warnings = run_standard(module, package, rows, keys)
        except Exception as exc:  # noqa: BLE001
            items, warnings = [], [f"{type(exc).__name__}: {exc}"]
        by_journal = defaultdict(list)
        for item in items or []:
            by_journal[item.get("journal_key")].append(item)
        for key in keys:
            journal = rows.get(key, {})
            name = journal.get("name") or key
            rows_items = by_journal.get(key, [])
            related = [value for value in warnings if key in value or name in value]
            warning = "; ".join(related)[:400] if related else ("" if rows_items else "0 items")
            flat = flatten(rows_items[0]) if rows_items else {}
            journal_rows.append({
                "package": package, "mode": mode, "journal_key": key, "journal_name": name,
                "status": "pass" if rows_items else "fail", "items": len(rows_items),
                "first_title": flat.get("title", ""), "authors": flat.get("authors", ""),
                "abstract_len": flat.get("abstract_len", 0), "doi": flat.get("doi", ""),
                "year": flat.get("year", ""), "issue": flat.get("issue", ""),
                "article_url": flat.get("url", ""), "pdf_url": flat.get("pdf_url", ""),
                "published_at": flat.get("published_at", ""), "warnings": warning,
            })
            for item in rows_items[:3]:
                data = flatten(item)
                item_rows.append({"package": package, "journal_key": key, "journal_name": name, **data})
        print(f"{package}: {len(keys)} journals, {len(items or [])} items, {len(warnings)} warnings", flush=True)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(journal_rows[0].keys()) if journal_rows else ["package"])
        writer.writeheader()
        writer.writerows(journal_rows)
    item_out = out.with_name(out.stem + "-items.csv")
    with item_out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(item_rows[0].keys()) if item_rows else ["package"])
        writer.writeheader()
        writer.writerows(item_rows)
    print("saved", out, "and", item_out)
    print("journals", len(journal_rows), "items", len(item_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
