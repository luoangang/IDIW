from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"
PLAN = ROOT / "journal_catalog" / "core" / "core-g7-additions-ready-2026-11-24.csv"
BACKUP = ROOT / ".local" / "backups" / "core-g7-apply-2026-11-24"
OUTPUT = ROOT / "journal_catalog" / "core" / "core-g7-additions-applied-2026-11-24.csv"
DATE = "2026-11-24"

VERSIONS = {"vsb_journals": "1.2.2", "hep_mirror_journals": "1.0.2", "custom_toc_journals": "3.3.0"}
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")


def norm(value):
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(value or "")).lower())


def core_tag(levels):
    mapping = {"来源期刊": "CSSCI", "扩展版": "CSSCI扩展", "北大核心": "北大核心",
               "CSTPCD": "科技核心", "CSCD": "CSCD"}
    parts = []
    for level in str(levels or "").split(";"):
        label = mapping.get(level.strip(), level.strip())
        if label and label not in parts:
            parts.append(label)
    return "核心:" + "/".join(parts[:2]) if parts else "核心:未分级"


def discipline_tag(categories):
    parts = [part.strip() for part in str(categories or "").split(";") if part.strip()]
    return "学科:" + "/".join(parts[:2]) if parts else "学科:未分类"


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
    package_rows = {}
    used_keys = set()
    existing_names = {}
    for package in VERSIONS:
        for filename in ("journals.json", "manifest.json"):
            shutil.copy2(ACADEMIC / package / filename, BACKUP / f"{package}-{filename}")
        data = json.loads((ACADEMIC / package / "journals.json").read_text(encoding="utf-8"))
        package_rows[package] = data if isinstance(data, list) else data.get("journals", [])
        for row in package_rows[package]:
            used_keys.add(row.get("journal_key"))
            existing_names.setdefault(package, set()).add(norm(row.get("name")))

    applied, skipped = [], []
    for row in rows:
        package = row["target_package"]
        if package not in VERSIONS:
            skipped.append((row["journal_name"], "unknown package"))
            continue
        name = row["journal_name"]
        if norm(name) in existing_names.get(package, set()):
            skipped.append((name, "duplicate name"))
            continue
        url = row.get("official_url") or row.get("current_url") or ""
        key = stable_key(name, url, used_keys)
        levels = row.get("core_levels", "")
        categories = row.get("categories", "")
        if package == "vsb_journals":
            tags = ["VSB", "采集:官网当期目次", "当期核验", "目录:核心", core_tag(levels), discipline_tag(categories)]
            entry = {
                "journal_key": key, "name": name, "url": url,
                "current_url": row.get("current_url", ""), "supplier": "VSB", "template_group": "vsb",
                "catalog_source": "core_2026-11-24", "data_source": "official_toc", "source_group": "vsb",
                "official_url": url, "verification_mode": "current_issue_html",
                "probe_items": int(float(row.get("items") or 0)), "probe_first_title": row.get("first_title", ""),
                "status": "verified", "data_source_detail": "官网当期目次 HTML", "tags": tags,
                "core_levels": levels, "categories": categories,
            }
        elif package == "hep_mirror_journals":
            tags = ["HEP", "采集:公开镜像", "非官网", "当期核验", "目录:核心", core_tag(levels), discipline_tag(categories)]
            entry = {
                "journal_key": key, "name": name, "url": url,
                "current_url": row.get("current_url", ""), "supplier": "HEP公开镜像", "template_group": "hep_mirror",
                "catalog_source": "core_2026-11-24", "data_source": "public_mirror", "source_group": "hep_mirror",
                "official_url": url, "verification_mode": "current_issue_html",
                "probe_items": int(float(row.get("items") or 0)), "probe_first_title": row.get("first_title", ""),
                "status": "verified", "data_source_detail": "HEP 公开镜像（非官网）", "tags": tags,
                "core_levels": levels, "categories": categories,
            }
        else:
            tags = ["采集:公开平台", "非官网", "当期核验", "目录:核心", core_tag(levels), discipline_tag(categories)]
            entry = {
                "journal_key": key, "name": name, "url": url,
                "current_url": row.get("current_url", ""), "supplier": "CAST公开平台", "template_group": "custom_toc",
                "evidence": "core_2026-11-24", "source_file": "", "catalog_source": "core_2026-11-24",
                "official_url": url, "data_source": "public_platform",
                "data_source_detail": "CAST 公开平台当期目次（非官网）", "source_group": "custom_toc",
                "status": "verified_current_issue", "verification_mode": "latest_issue", "verified_at": DATE,
                "probe_items": int(float(row.get("items") or 0)), "probe_first_title": row.get("first_title", ""),
                "core_levels": levels, "categories": categories, "tags": tags,
            }
        package_rows[package].append(entry)
        existing_names.setdefault(package, set()).add(norm(name))
        applied.append({
            "journal_name": name, "journal_key": key, "target_package": package,
            "items": row.get("items", ""), "first_title": row.get("first_title", ""),
            "core_levels": levels, "categories": categories,
            "official_url": url, "current_url": row.get("current_url", ""), "platform": row.get("platform", ""),
        })

    for package, data_rows in package_rows.items():
        (ACADEMIC / package / "journals.json").write_text(
            json.dumps(data_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_path = ACADEMIC / package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["package_version"] = VERSIONS[package]
        if package == "custom_toc_journals":
            prop = manifest["parameters_schema"]["properties"]["journal_keys"]
            prop["maxItems"] = max(int(prop.get("maxItems", 500)), len(data_rows) + 10)
            default = prop["default"]
            for entry in applied:
                if entry["target_package"] == package and entry["journal_key"] not in default:
                    default.append(entry["journal_key"])
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(applied[0].keys()) if applied else ["journal_name"])
        writer.writeheader()
        writer.writerows(applied)
    print("applied", len(applied), Counter(row["target_package"] for row in applied))
    print("skipped", len(skipped), skipped)
    print("saved", OUTPUT)
    print("backup", BACKUP)


if __name__ == "__main__":
    raise SystemExit(main())
