"""Restrict deliverable journal catalogs to evidence-backed choices."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "journal_catalog" / "journal-capacity-70-2026-10-29.csv"
ACADEMIC = ROOT / "crawler_packages" / "academic"
MAGETECH_EXCEPTIONS = {"54d332e80c1aa5a1", "32ee319e8c2ea670"}
QBZL_CATALOG_KEY = "1550406c8b34d28e"
BUILTIN_ROWS = (
    {"source_row": None, "journal_key": "data_analysis", "name": "数据分析与知识发现",
     "url": "https://manu44.magtech.com.cn/Jwk_infotech_wk3/CN/home", "supplier": "玛格泰克",
     "template_group": "magetech", "url_signature": None, "evidence": "verified_builtin"},
    {"source_row": None, "journal_key": "lis", "name": "图书情报工作",
     "url": "https://www.lis.ac.cn/CN/0252-3116/home.shtml", "supplier": "玛格泰克",
     "template_group": "magetech", "url_signature": None, "evidence": "verified_builtin"},
)


def audited_keys() -> dict[str, set[str]]:
    with AUDIT.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    cbpt = {row["journal_key"] for row in rows if row["package_key"] == "cnki_cbpt"}
    magetech = {row["journal_key"] for row in rows if row["package_key"] == "magetech_journals" and row["status"] == "reached_70"}
    magetech.update(MAGETECH_EXCEPTIONS)
    if len(cbpt) != 509 or len(magetech) != 98:
        raise ValueError("audit counts changed; review selection before pruning")
    return {"cnki_cbpt": cbpt, "magetech_journals": magetech}


def prune() -> tuple[dict[str, list[dict]], list[dict]]:
    allowed = audited_keys()
    catalogs, removed = {}, []
    for package_key, keys in allowed.items():
        path = ACADEMIC / package_key / "journals.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        kept = []
        for row in rows:
            is_qbzl = package_key == "magetech_journals" and row["name"] == "情报资料工作"
            if row["journal_key"] in keys or (is_qbzl and QBZL_CATALOG_KEY in keys):
                if is_qbzl:
                    row = {**row, "journal_key": "qbzl"}
                kept.append(row)
            else:
                removed.append({"package_key": package_key, "journal_key": row["journal_key"],
                                "name": row["name"], "reason": "not_in_verified_selection"})
        if package_key == "magetech_journals":
            known = {row["journal_key"] for row in kept}
            kept = [row for row in BUILTIN_ROWS if row["journal_key"] not in known] + kept
        expected = 509 if package_key == "cnki_cbpt" else 98
        if len(kept) != expected or len({row["journal_key"] for row in kept}) != expected:
            raise ValueError(f"unexpected retained count for {package_key}: {len(kept)}")
        catalogs[package_key] = kept
    return catalogs, removed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    catalogs, removed = prune()
    for key, rows in catalogs.items():
        print(f"{key}: keep {len(rows)}")
    print(f"remove: {len(removed)} candidates")
    if not args.apply:
        return
    for key, rows in catalogs.items():
        (ACADEMIC / key / "journals.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    path = ROOT / "journal_catalog" / "removed-from-package-catalogs-2026-10-30.csv"
    if not path.exists():
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["package_key", "journal_key", "name", "reason"])
            writer.writeheader()
            writer.writerows(removed)


if __name__ == "__main__":
    main()
