from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"
PLAN = ROOT / "journal_catalog" / "core" / "c-group" / "c-main-writeback-2026-11-24.csv"
OUTPUT = ROOT / "journal_catalog" / "core" / "c-group" / "c-main-applied-2026-11-24.csv"
BACKUP = ROOT / ".local" / "backups" / "c-group-main-apply-2026-11-24"
DATE = "2026-11-24"
EVIDENCE = "c_group_main_2026-11-24"
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")
VERSIONS = {"custom_toc_journals": "3.8.0", "magetech_journals": "1.15.0", "paperonce_journals": "1.1.0"}
SOURCE_GROUP = {"custom_toc_journals": "custom_toc", "magetech_journals": "magetech", "paperonce_journals": "paperonce"}


def norm(value):
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(value or "")).lower())


def stable_key(name, url, used):
    for salt in range(50):
        raw = f"{norm(name)}|{url}|{salt}"
        key = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        if key not in used:
            used.add(key)
            return key
    raise RuntimeError("cannot allocate journal key")


def main():
    rows = list(csv.DictReader(PLAN.open(encoding="utf-8-sig")))
    BACKUP.mkdir(parents=True, exist_ok=True)
    packages = {}
    for target in VERSIONS:
        path = ACADEMIC / target
        for filename in ("journals.json", "manifest.json"):
            shutil.copy2(path / filename, BACKUP / f"{target}-{filename}")
        journals = json.loads((path / "journals.json").read_text(encoding="utf-8"))
        packages[target] = {"path": path, "journals": journals,
                            "used": {row.get("journal_key") for row in journals},
                            "names": {norm(row.get("name")) for row in journals}}
    applied, skipped = [], []
    for row in rows:
        target = row["target_package"]
        state = packages[target]
        name = row["journal_name"]
        if norm(name) in state["names"]:
            skipped.append((name, "duplicate name"))
            continue
        url = row.get("official_url") or row.get("current_url") or ""
        if target == "paperonce_journals":
            parts = urlsplit(url or row.get("current_url") or "")
            url = f"{parts.scheme}://{parts.netloc}"
        key = stable_key(name, url, state["used"])
        entry = {
            "journal_key": key, "name": name, "url": url,
            "current_url": row.get("current_url", ""),
            "supplier": row.get("supplier", "官网"),
            "template_group": row.get("template_group", "custom_toc"),
            "evidence": EVIDENCE, "source_file": "c-main-verify-2026-11-24.csv",
            "catalog_source": "core_2026-11-24", "official_url": row.get("official_url", ""),
            "data_source": row.get("data_source", "official_site"),
            "data_source_detail": row.get("data_source_detail", ""),
            "source_group": SOURCE_GROUP[target],
            "status": "verified_current_issue", "verification_mode": "latest_issue",
            "verified_at": DATE, "probe_items": int(float(row.get("items") or 0)),
            "probe_first_title": row.get("first_title", ""),
            "core_levels": row.get("core_levels", ""), "categories": row.get("categories", ""),
            "tags": [value for value in row.get("tags", "").split(";") if value],
        }
        if row.get("note"):
            entry["data_source_detail"] = (entry["data_source_detail"] + "；" + row["note"])[:300]
        if target == "paperonce_journals":
            entry["data_source_detail"] = "PaperOnce LastIssueList API（官网接口，非页面）"
        state["journals"].append(entry)
        state["names"].add(norm(name))
        applied.append({"journal_name": name, "journal_key": key, "target_package": target,
                        "items": row.get("items", ""), "first_title": row.get("first_title", ""),
                        "core_levels": row.get("core_levels", ""), "categories": row.get("categories", ""),
                        "official_url": row.get("official_url", ""), "current_url": row.get("current_url", ""),
                        "data_source": entry["data_source"]})
    for target, state in packages.items():
        package = state["path"]
        journals = state["journals"]
        (package / "journals.json").write_text(json.dumps(journals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["package_version"] = VERSIONS[target]
        prop = manifest["parameters_schema"]["properties"]["journal_keys"]
        default = prop["default"]
        for row in applied:
            if row["target_package"] == target and row["journal_key"] not in default:
                default.append(row["journal_key"])
        if target == "custom_toc_journals":
            prop["maxItems"] = max(int(prop.get("maxItems", 30)), len(journals) + 10, len(default))
        else:
            prop["maxItems"] = max(int(prop.get("maxItems", 30)), len(default))
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(target, "catalog", len(journals), "version", manifest["package_version"],
              "maxItems", prop["maxItems"], "default", len(default))
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(applied[0].keys()) if applied else ["journal_name"])
        writer.writeheader()
        writer.writerows(applied)
    print("applied", len(applied), Counter(row["target_package"] for row in applied))
    print("skipped", len(skipped), skipped)
    print("saved", OUTPUT)
    print("backup", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
