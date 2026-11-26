from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import build_opener


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"
INPUT = ROOT / "journal_catalog" / "core" / "workbuddy" / "b-retry-results-2026-11-24.csv"
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


def package_guess(row):
    platform = str(row.get("platform") or "").strip().lower()
    url = (row.get("current_url") or row.get("official_url") or "").lower()
    if "cbpt.cnki.net" in url or "cnki" in platform:
        return "cnki_cbpt"
    if "paperonce.org" in url or "paperopen.com" in url or "paperonce" in platform or "paperopen" in platform:
        return "paperonce"
    if "rc-pub" in url or "founder" in platform:
        return "founder"
    if "cjournal.hep.com.cn" in url or platform == "hep":
        return "hep"
    if "sancai" in platform:
        return "sancai"
    if "qinyun" in platform:
        return "qinyun"
    if "rhhz" in platform or "rhzh" in platform:
        return "rhzh"
    if "magetech" in platform or "magtech" in platform or "margetech" in platform or "magnetech" in platform:
        return "magetech"
    if "/cn/" in url and ("current" in url or "/cn/y" in url or re.search(r"/cn/10\.", url)):
        return "magetech"
    return "custom"


def base_journal(row, key):
    url = row.get("official_url") or row.get("current_url") or ""
    current = row.get("current_url") or url
    return {
        "journal_key": key,
        "name": row["journal_name"],
        "url": url,
        "current_url": current,
    }


def collect_module(module, key, journal, timeout=25):
    request = {
        "query": "x",
        "limit": 60,
        "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                       "per_journal_limit": 60, "timeout_seconds": timeout},
    }
    items, warnings, _ = module.collect(request, {key: journal})
    return items, "; ".join(str(value) for value in warnings)[:300]


def magetech_items(module, key, journal, timeout):
    journal_obj = module.journal_from_catalog(journal)
    page = module.fetch_current_issue(build_opener(), journal_obj, timeout)
    items = module.parse_search_result(page, journal_obj) or module.parse_generic_toc(page, journal_obj)
    return items or [], ""


def run_attempt(parser, modules, key, journal, timeout):
    try:
        if parser == "magetech":
            items, error = magetech_items(modules["magetech"], key, journal, timeout)
        elif parser == "custom":
            items, error = collect_module(modules["custom"], key, journal, timeout)
        elif parser == "cnki_cbpt":
            items, error = collect_module(modules["cnki_cbpt"], key, journal, timeout)
        elif parser == "qinyun":
            items, error = collect_module(modules["qinyun"], key, journal, timeout)
        elif parser == "rhzh":
            items, error = collect_module(modules["rhzh"], key, journal, timeout)
        elif parser == "paperonce":
            probe = dict(journal)
            parts = urlsplit(journal["current_url"] or journal["url"])
            probe["url"] = f"{parts.scheme}://{parts.netloc}"
            items, error = collect_module(modules["paperonce"], key, probe, timeout)
        elif parser == "hep":
            items, error = collect_module(modules["hep"], key, journal, timeout)
        elif parser == "sancai":
            items, error = collect_module(modules["sancai"], key, journal, timeout)
        else:
            return [], f"unknown parser {parser}"
        return list(items or []), error
    except Exception as exc:  # noqa: BLE001 - report raw failure
        return [], f"{type(exc).__name__}: {exc}"


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--select", default="", help="逗号分隔的 package_guess 过滤")
    cli.add_argument("--limit", type=int, default=0)
    cli.add_argument("--offset", type=int, default=0)
    cli.add_argument("--timeout", type=int, default=25)
    cli.add_argument("--attempts", type=int, default=2)
    cli.add_argument("--no-fallback", action="store_true")
    cli.add_argument("--output", default=str(ROOT / ".local" / "core" / "workbuddy-b-verify-2026-11-24.csv"))
    args = cli.parse_args()

    modules = {
        "custom": load(ACADEMIC / "custom_toc_journals" / "crawler.py", "b_custom"),
        "magetech": load(ACADEMIC / "magetech_journals" / "crawler.py", "b_magetech"),
        "cnki_cbpt": load(ACADEMIC / "cnki_cbpt" / "crawler.py", "b_cbpt"),
        "qinyun": load(ACADEMIC / "qinyun_journals" / "crawler.py", "b_qinyun"),
        "rhzh": load(ACADEMIC / "rhzh_journals" / "crawler.py", "b_rhzh"),
        "paperonce": load(ACADEMIC / "paperonce_journals" / "crawler.py", "b_paperonce"),
        "hep": load(ACADEMIC / "hep_mirror_journals" / "crawler.py", "b_hep"),
        "sancai": load(ACADEMIC / "sancai_journals" / "crawler.py", "b_sancai"),
    }
    rows = [row for row in csv.DictReader(INPUT.open(encoding="utf-8-sig")) if row["status"] == "ok_current"]
    if args.select:
        wanted = {value.strip() for value in args.select.split(",") if value.strip()}
        rows = [row for row in rows if package_guess(row) in wanted]
    if args.offset:
        rows = rows[args.offset:]
    if args.limit:
        rows = rows[:args.limit]

    report = []
    for index, row in enumerate(rows, 1):
        key = f"b{index:04d}"
        guess = package_guess(row)
        journal = base_journal(row, key)
        attempts = []
        primary_order = [guess] if guess != "founder" else ["custom"]
        if not args.no_fallback:
            for fallback in ("custom", "magetech", "cnki_cbpt"):
                if fallback not in primary_order:
                    primary_order.append(fallback)
        items, parser_used, error = [], "", ""
        for parser in primary_order:
            for attempt in range(args.attempts):
                items, error = run_attempt(parser, modules, key, journal, args.timeout)
                attempts.append(f"{parser}#{attempt + 1}:{len(items)}")
                if items:
                    parser_used = parser
                    break
                if attempt < args.attempts - 1:
                    time.sleep(2)
            if items:
                break
        matched = title_match(row.get("first_title"), items)
        status = "pass" if items and matched else ("warn" if items else "fail")
        report.append({
            "journal_name": row["journal_name"],
            "batch": row.get("batch", ""),
            "platform_raw": row.get("platform", ""),
            "package_guess": guess,
            "verified_parser": parser_used,
            "status": status,
            "items": len(items),
            "workbuddy_items": row.get("current_items", ""),
            "first_title": (items[0].get("title", "") if items else "")[:160],
            "workbuddy_first_title": row.get("first_title", "")[:160],
            "title_match": "yes" if matched else "no",
            "current_url": row.get("current_url", ""),
            "official_url": row.get("official_url", ""),
            "attempts": ";".join(attempts[:8]),
            "warnings": error[:300],
        })
        print(f"{index}/{len(rows)} {status} {len(items)} {row['journal_name']} | {guess}->{parser_used or '-'} | {report[-1]['first_title'][:50]} | {error[:80]}", flush=True)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report[0].keys()) if report else ["journal_name"])
        writer.writeheader()
        writer.writerows(report)
    print("saved", out)
    from collections import Counter
    print("summary", dict(Counter(row["status"] for row in report)))
    print("parsers", dict(Counter(row["verified_parser"] for row in report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
