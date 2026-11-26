from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def host(url):
    return (urlsplit(url).hostname or "").lower()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "journal_catalog" / "core" / "core-probe-results-2026-11-22.csv"))
    parser.add_argument("--output", default=str(ROOT / ".local" / "core" / "probe-verify-2026-11-22.csv"))
    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    rows = [row for row in csv.DictReader(input_path.open(encoding="utf-8-sig"))
            if row.get("status") in ("ok_current", "ok_current_search")]

    ct = load(ACADEMIC / "custom_toc_journals" / "crawler.py", "verify_ct")
    mg = load(ACADEMIC / "magetech_journals" / "crawler.py", "verify_mg")
    cb = load(ACADEMIC / "cnki_cbpt" / "crawler.py", "verify_cb")
    qy = load(ACADEMIC / "qinyun_journals" / "crawler.py", "verify_qy")
    rh = load(ACADEMIC / "rhzh_journals" / "crawler.py", "verify_rh")
    vs = load(ACADEMIC / "vsb_journals" / "crawler.py", "verify_vs")

    from urllib.request import build_opener
    output = []
    for index, row in enumerate(rows):
        key = f"p{index:015d}"
        name = row["journal_name"]
        official = row.get("official_url", "")
        current = row.get("current_url", "")
        platform = row.get("platform_key", "")
        parser, items, warnings = "", [], ""
        try:
            if platform == "magetech":
                journal = mg.journal_from_catalog({"journal_key": key, "name": name, "url": official, "current_url": current})
                page = mg.fetch_current_issue(build_opener(), journal, 25)
                items = mg.parse_search_result(page, journal) or mg.parse_generic_toc(page, journal)
                parser = "magetech"
            elif platform == "cnki_cbpt" and host(official).endswith(".cbpt.cnki.net"):
                journal = {"journal_key": key, "name": name, "url": official, "current_url": current}
                request = {"query": "x", "limit": 50, "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 50, "timeout_seconds": 25}}
                items, warnings, _ = cb.collect(request, {key: journal})
                parser = "cnki_cbpt"
            elif platform == "qinyun":
                journal = {"journal_key": key, "name": name, "url": official, "current_url": current}
                request = {"query": "x", "limit": 50, "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 50, "timeout_seconds": 25}}
                items, warnings, _ = qy.collect(request, {key: journal})
                parser = "qinyun"
            elif platform == "rhzh":
                journal = {"journal_key": key, "name": name, "url": official, "current_url": current}
                request = {"query": "x", "limit": 50, "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 50, "timeout_seconds": 25}}
                items, warnings, _ = rh.collect(request, {key: journal})
                parser = "rhzh"
            elif platform == "vsb":
                journal = {"journal_key": key, "name": name, "url": official, "current_url": current}
                items = vs.parse_toc(vs.read_page(journal, 25), journal)
                parser = "vsb"
            else:
                journal = {"journal_key": key, "name": name, "url": official, "current_url": current}
                items = ct.parse_toc(ct.read_page(journal, 25), journal)
                parser = "custom_toc"
        except Exception as exc:
            warnings = f"{type(exc).__name__}: {exc}"
        first = items[0].get("title", "") if items else ""
        output.append({
            "journal_name": name, "platform": platform, "parser": parser,
            "items": len(items), "first_title": first[:120],
            "warnings": str(warnings)[:300], "official_url": official, "current_url": current,
        })

    fields = ["journal_name", "platform", "parser", "items", "first_title", "warnings", "official_url", "current_url"]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    for row in output:
        print(f"{row['items']:>3} {row['parser']:12s} {row['journal_name']} | {row['first_title']} | {row['warnings']}")
    print("saved", output_path)


if __name__ == "__main__":
    main()