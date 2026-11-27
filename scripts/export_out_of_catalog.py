from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"
CATALOG = ROOT / "journal_catalog" / "journals.json"
DATE = "2026-11-25"
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")


def norm(value):
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(value or "")).lower())


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog_keys = {row["journal_key"] for row in catalog}
    catalog_names = {norm(row["name"]) for row in catalog}
    rows = []
    for path in sorted(ACADEMIC.glob("*/journals.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("journals", [])
        for row in data:
            key, name = row.get("journal_key"), row.get("name")
            if key in catalog_keys or norm(name) in catalog_names:
                continue
            catalog_source = row.get("catalog_source", "")
            source = ("core_list_" + catalog_source[len("core_"):]
                      if catalog_source.startswith("core_2026-") else "builtin_not_in_2377")
            rows.append({
                "journal_key": key,
                "name": name,
                "package": path.parent.name,
                "source": source,
                "catalog_source": row.get("catalog_source", ""),
                "core_levels": row.get("core_levels", ""),
                "categories": row.get("categories", ""),
                "official_url": row.get("official_url") or row.get("url", ""),
                "current_url": row.get("current_url", ""),
                "probe_items": row.get("probe_items", ""),
                "probe_first_title": row.get("probe_first_title", ""),
                "status": row.get("status", ""),
                "tags": ";".join(row.get("tags") or []),
            })
    rows.sort(key=lambda row: (row["source"], row["package"], row["name"]))
    output = ROOT / "journal_catalog" / f"out-of-2377-journals-{DATE}.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["journal_key"])
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "date": DATE,
        "total": len(rows),
        "by_source": dict(Counter(row["source"] for row in rows)),
        "by_package": dict(Counter(row["package"] for row in rows).most_common()),
        "csv": str(output),
    }
    (output.with_suffix(".json")).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for row in rows:
        print(row["source"], row["package"], row["name"], "|", row["core_levels"], "|", row["categories"])


if __name__ == "__main__":
    main()