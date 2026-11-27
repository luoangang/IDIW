from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.request import build_opener


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"
CORE = ROOT / "journal_catalog" / "core"

PACKAGE_FILES = {
    "cnki_cbpt": "cnki_cbpt",
    "magetech_journals": "magetech_journals",
    "custom_toc_journals": "custom_toc_journals",
    "qinyun_journals": "qinyun_journals",
    "rhzh_journals": "rhzh_journals",
    "founder_journals": "founder_journals",
    "supplement_journals": "supplement_journals",
    "vsb_journals": "vsb_journals",
    "hep_mirror_journals": "hep_mirror_journals",
    "paperonce_journals": "paperonce_journals",
}


def load_module(package):
    name = f"smoke_{package}"
    if name in sys.modules:
        return sys.modules[name]
    path = ACADEMIC / package / "crawler.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_catalog(package):
    path = ACADEMIC / package / "journals.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("journals", [])
    return {row.get("journal_key"): row for row in rows}


def make_request(key, limit):
    return {
        "query": "x",
        "limit": limit,
        "parameters": {
            "journal_keys": [key],
            "collect_mode": "latest_issue",
            "per_journal_limit": limit,
            "timeout_seconds": 25,
        },
    }


def run_one(package, module, journal, limit):
    key = journal["journal_key"]
    if package == "custom_toc_journals":
        items, warnings, _ = module.collect(make_request(key, limit), {key: journal})
        return items, warnings
    if package == "magetech_journals":
        journal_obj = module.journal_from_catalog(journal)
        page = module.fetch_current_issue(build_opener(), journal_obj, 25)
        try:
            items = module.parse_search_result(page, journal_obj)
        except ValueError:
            items = []
        generic = module.parse_generic_toc(page, journal_obj)
        if not items or (len(generic) > len(items) and len(items) < 3):
            items = generic
        return items, ""
    if package == "founder_journals":
        items, warnings, _ = module.collect(make_request(key, limit), {key: journal})
        return items, warnings
    if package == "cnki_cbpt":
        items, warnings, _ = module.collect(make_request(key, limit), {key: journal})
        return items, warnings
    if package == "qinyun_journals":
        items, warnings, _ = module.collect(make_request(key, limit), {key: journal})
        return items, warnings
    if package == "paperonce_journals":
        items, warnings, _ = module.collect(make_request(key, limit), {key: journal})
        return items, warnings
    if package == "rhzh_journals":
        items, warnings, _ = module.collect(make_request(key, limit), {key: journal})
        return items, warnings
    if package == "supplement_journals":
        request = make_request(key, limit)
        request["parameters"]["lookback_days"] = 365
        items, warnings, _ = module.collect(request)
        return items, warnings
    if package in ("vsb_journals", "hep_mirror_journals"):
        items, warnings, _ = module.collect(make_request(key, limit), {key: journal})
        return items, warnings
    raise ValueError(f"unsupported package {package}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--applied", required=True, help="写入后的 applied CSV")
    parser.add_argument("--per-package", type=int, default=4)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--date", default="2026-11-23")
    args = parser.parse_args()

    applied_path = Path(args.applied)
    if not applied_path.is_absolute():
        applied_path = ROOT / applied_path
    with applied_path.open(encoding="utf-8-sig", newline="") as handle:
        applied = list(csv.DictReader(handle))

    by_package = {}
    for row in applied:
        package = row.get("target_package")
        if package in PACKAGE_FILES:
            by_package.setdefault(package, []).append(row)

    report = []
    for package, rows in by_package.items():
        module = load_module(package)
        catalog = load_catalog(package)
        step = max(1, len(rows) // args.per_package)
        sample = rows[::step][: args.per_package]
        for row in sample:
            key = row.get("journal_key")
            journal = catalog.get(key)
            if not journal:
                report.append({
                    "package": package, "journal_name": row.get("journal_name", ""),
                    "journal_key": key, "status": "fail", "items": 0,
                    "first_title": "", "url": "", "warnings": "catalog row not found",
                })
                continue
            items, warnings, error = [], "", ""
            for attempt in range(args.retries + 1):
                try:
                    items, warnings = run_one(package, module, journal, args.limit)
                except Exception as exc:  # noqa: BLE001 - smoke report keeps raw error
                    items, warnings = [], f"{type(exc).__name__}: {exc}"
                if items:
                    break
            first = items[0].get("title", "") if items else ""
            if items:
                status = "pass" if not warnings else "warn"
            else:
                status = "fail"
            report.append({
                "package": package, "journal_name": row.get("journal_name", ""),
                "journal_key": key, "status": status, "items": len(items),
                "first_title": first[:120], "url": journal.get("current_url") or journal.get("url", ""),
                "warnings": str(warnings)[:300],
            })

    out_path = CORE / f"core-smoke-{args.date}.csv"
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["package", "journal_name", "journal_key", "status", "items", "first_title", "url", "warnings"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report)

    counts = Counter(row["status"] for row in report)
    print("smoke", len(report), dict(counts))
    for row in report:
        print(f"{row['status']:4s} {row['package']:26s} {row['items']:3d} {row['journal_name']} | {row['first_title'][:50]} | {row['warnings'][:80]}")
    print("saved", out_path)
    return 0 if counts.get("fail", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
