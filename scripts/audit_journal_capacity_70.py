"""Recheck each previously verified Chinese journal for 70 valid distinct records."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.protocol import identity_digest, load_manifest, validate_item, validate_parameters


PACKAGES = ("magetech_journals", "cnki_cbpt", "qinyun_journals", "rhzh_journals", "sancai_journals")
PACKAGE_ROOT = ROOT / "crawler_packages" / "academic"


def load_targets():
    targets = []
    for package_key in PACKAGES:
        package_dir = PACKAGE_ROOT / package_key
        module = importlib.import_module(f"crawler_packages.academic.{package_key}.crawler")
        manifest = load_manifest(package_dir)
        catalog = json.loads((package_dir / "journals.json").read_text(encoding="utf-8"))
        by_key = {row["journal_key"]: row for row in catalog}
        if package_key == "magetech_journals":
            audited = json.loads((ROOT / "journal_catalog" / "audit-magetech-final-2026-10-23.json").read_text(encoding="utf-8"))
            keys = [row["journal_key"] for row in audited if row["status"] == "passed_with_items"]
            keys += ["data_analysis", "lis"]
        elif package_key == "cnki_cbpt":
            audited = json.loads((ROOT / "journal_catalog" / "audit-cbpt-final-2026-10-23.json").read_text(encoding="utf-8"))
            keys = [row["journal_key"] for row in audited if row["status"] == "passed_with_items"]
        else:
            keys = list(by_key)
        for key in keys:
            journal = by_key.get(key)
            if package_key == "magetech_journals" and journal is None:
                builtin = module.JOURNALS[key]
                journal = {"journal_key": key, "name": builtin.name, "url": builtin.base_url}
            if journal is None:
                raise ValueError(f"verified journal not present in package: {package_key}/{key}")
            targets.append((package_key, key, journal, module, manifest))
    names = [journal["name"] for _, _, journal, _, _ in targets]
    if len(targets) != 925 or len(set(names)) != 925:
        raise ValueError(f"expected 925 distinct verified journals, found {len(targets)} entries / {len(set(names))} names")
    return targets


def probe(target, query, timeout):
    package_key, key, journal, module, manifest = target
    started = time.monotonic()
    result = {
        "package_key": package_key, "journal_key": key, "name": journal["name"], "url": journal["url"],
        "query": query, "status": "failed", "valid_count": 0, "returned_count": 0,
        "warnings": [], "error": None, "elapsed_seconds": None,
        "tested_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        settings = {"journal_keys": [key]}
        if package_key == "magetech_journals":
            settings.update({"max_pages_per_journal": 20, "request_delay_ms": 300})
        else:
            settings.update({"per_journal_limit": 70, "timeout_seconds": timeout})
        request = {
            "query": query, "aliases": [], "limit": 70,
            "parameters": validate_parameters(manifest.parameters_schema, settings),
            "time_range": {"from": None, "to": None},
            "deadline_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        }
        if package_key == "magetech_journals":
            items, warnings, successes = module.collect(request)
        else:
            items, warnings, successes = module.collect(request, {key: journal})
        result["returned_count"] = len(items)
        result["warnings"] = warnings[:3]
        unique = set()
        for item in items:
            valid = validate_item(manifest, item)
            unique.add(identity_digest(manifest, valid))
        result["valid_count"] = len(unique)
        if successes and len(unique) >= 70:
            result["status"] = "reached_70"
        elif successes:
            result["status"] = "under_70"
        else:
            result["error"] = "no successful source response"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="研究")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--sample-per-package", type=int, default=0)
    parser.add_argument("--only-package", action="append", choices=PACKAGES, default=[])
    parser.add_argument("--recheck-package", action="append", choices=PACKAGES, default=[])
    parser.add_argument("--recheck-status", action="append", choices=["reached_70", "under_70", "failed"], default=[])
    parser.add_argument("--output", type=Path, default=ROOT / "journal_catalog" / "audit-capacity-70-2026-10-28.jsonl")
    args = parser.parse_args()
    if not 1 <= args.workers <= 6 or not 5 <= args.timeout <= 60:
        parser.error("workers must be 1..6 and timeout 5..60")
    targets = load_targets()
    if args.only_package:
        targets = [target for target in targets if target[0] in args.only_package]
    if args.sample_per_package:
        seen = {package: 0 for package in PACKAGES}
        selected = []
        for target in targets:
            if seen[target[0]] < args.sample_per_package:
                selected.append(target)
                seen[target[0]] += 1
        targets = selected
    completed = {}
    if args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                completed[(row["package_key"], row["journal_key"], row["query"])] = row["status"]
    if args.recheck_status:
        targets = [target for target in targets if completed.get((target[0], target[1], args.query)) in args.recheck_status]
    else:
        targets = [target for target in targets if target[0] in args.recheck_package
                   or (target[0], target[1], args.query) not in completed]
    print(json.dumps({"remaining": len(targets), "already_recorded": len(completed), "output": str(args.output)}, ensure_ascii=False), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts = {"reached_70": 0, "under_70": 0, "failed": 0}
    with args.output.open("a", encoding="utf-8") as handle, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(probe, target, args.query, args.timeout) for target in targets]
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            counts[result["status"]] += 1
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
            if index % 10 == 0 or index == len(futures):
                print(json.dumps({"done": index, "total": len(futures), "counts": counts}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
