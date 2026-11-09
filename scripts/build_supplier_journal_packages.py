"""Build standalone journal catalogs from the classified workbook export."""

from __future__ import annotations

import json
import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "qinyun_journals": ("qinyun_8329130d.json", "勤云"),
    "rhzh_journals": ("rhzh_d203fcbb.json", "仁和汇智"),
    "sancai_journals": ("vendor_45577080.json", "西安三才"),
}


def candidate_rows(package_key: str) -> list[dict]:
    filename, supplier = GROUPS[package_key]
    source = ROOT / "journal_catalog" / "groups" / filename
    rows = json.loads(source.read_text(encoding="utf-8"))
    assert all(row["supplier"] == supplier for row in rows)
    if package_key == "qinyun_journals":
        rows.append({
            "source_row": None,
            "journal_key": "jos",
            "name": "软件学报",
            "url": "https://jos.org.cn",
            "supplier": "勤云",
            "template_group": "qinyun",
            "url_signature": "jos.org.cn",
            "evidence": "live_search_verified",
            "publisher": "jos",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verified-only", action="store_true")
    args = parser.parse_args()
    verified = {}
    if args.verified_only:
        report = ROOT / "journal_catalog" / "supplier-journal-audit-2026-10-26.csv"
        with report.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["status"] == "verified":
                    verified.setdefault(row["package"], set()).add(row["journal_key"])
    for package_key in GROUPS:
        rows = candidate_rows(package_key)
        if args.verified_only:
            rows = [row for row in rows if row["journal_key"] in verified.get(package_key, set())]
        target = ROOT / "crawler_packages" / "academic" / package_key / "journals.json"
        target.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{package_key}: {len(rows)} candidates -> {target}")


if __name__ == "__main__":
    main()
