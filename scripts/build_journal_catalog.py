"""Classify the supplied journal workbook without guessing crawler compatibility."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from itertools import groupby
from pathlib import Path
import re
from urllib.parse import urlsplit

from openpyxl import load_workbook


EXCLUDED_SUPPLIERS = {"独立/其他官网（供应商未知）", "网页过期/停刊或无法访问"}
TEMPLATE_GROUPS = {
    "同方知网": "cnki",
    "勤云": "qinyun",
    "玛格泰克": "magetech",
    "仁和汇智": "rhzh",
    "北大方正": "founder",
    "PaperOnce": "paperonce",
    "VSB": "vsb",
    "中华医学会": "yiigle",
}


def classify(name, url, supplier, row_number):
    if not all(isinstance(value, str) and value.strip() for value in (name, url, supplier)):
        return None
    name, url, supplier = name.strip(), url.strip(), supplier.strip()
    if supplier in EXCLUDED_SUPPLIERS:
        return None
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    group = TEMPLATE_GROUPS.get(supplier, supplier)
    signature = None
    host = parsed.hostname.lower()
    if group == "cnki" and host.endswith(".cbpt.cnki.net"):
        signature = "cbpt.cnki.net"
        group = "cnki_cbpt"
    elif group == "magetech" and "magtech" in host:
        signature = "magtech hostname"
    elif group == "rhzh" and host.endswith(".xml-journal.net"):
        signature = "xml-journal.net"
    elif group == "paperonce" and "paperonce" in host:
        signature = "paperonce hostname"
    elif group == "yiigle" and host.endswith(".yiigle.com"):
        signature = "yiigle.com"
    return {
        "source_row": row_number, "journal_key": hashlib.sha256(url.lower().encode("utf-8")).hexdigest()[:16],
        "name": name, "url": url, "supplier": supplier,
        "template_group": group, "url_signature": signature,
        "evidence": "url_signature" if signature else "supplier_label_only",
    }


def build(
    workbook_path: Path, output_dir: Path,
    cbpt_package_dir: Path | None = None,
    magetech_package_dir: Path | None = None,
) -> dict:
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    sheet = workbook["表1"]
    records = []
    excluded = 0
    for row_number, (name, url, supplier) in enumerate(sheet.iter_rows(min_row=2, max_col=3, values_only=True), 2):
        record = classify(name, url, supplier, row_number)
        if record is None:
            excluded += 1
        else:
            records.append(record)
    records.sort(key=lambda row: (row["template_group"], row["name"], row["url"]))
    groups = Counter(row["template_group"] for row in records)
    suppliers = Counter(row["supplier"] for row in records)
    summary = {
        "source": workbook_path.name,
        "included": len(records), "excluded": excluded,
        "groups": dict(sorted(groups.items())),
        "suppliers": dict(sorted(suppliers.items())),
        "url_signature_count": sum(row["url_signature"] is not None for row in records),
        "supplier_only_count": sum(row["url_signature"] is None for row in records),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "journals.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    groups_dir = output_dir / "groups"
    groups_dir.mkdir(parents=True, exist_ok=True)
    group_index = []
    for group, members in groupby(records, key=lambda record: record["template_group"]):
        rows = list(members)
        safe_name = re.sub(r"[^a-z0-9_]+", "_", group.lower()).strip("_")
        filename = f"{safe_name or 'vendor'}_{hashlib.sha256(group.encode('utf-8')).hexdigest()[:8]}.json"
        (groups_dir / filename).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        group_index.append({"group": group, "file": filename, "count": len(rows)})
    (groups_dir / "index.json").write_text(
        json.dumps(group_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if cbpt_package_dir is not None:
        cbpt_package_dir.mkdir(parents=True, exist_ok=True)
        cbpt_records = [record for record in records if record["template_group"] == "cnki_cbpt"]
        (cbpt_package_dir / "journals.json").write_text(
            json.dumps(cbpt_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if magetech_package_dir is not None:
        magetech_package_dir.mkdir(parents=True, exist_ok=True)
        magetech_records = [record for record in records if record["supplier"] == "玛格泰克"]
        (magetech_package_dir / "journals.json").write_text(
            json.dumps(magetech_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path, default=Path("journal_catalog"))
    parser.add_argument("--cbpt-package-dir", type=Path)
    parser.add_argument("--magetech-package-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.workbook, args.output, args.cbpt_package_dir, args.magetech_package_dir), ensure_ascii=False, indent=2))
