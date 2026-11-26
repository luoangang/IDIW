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
REVIEW = ROOT / ".local" / "core" / "review-verify-2026-11-22.csv"
APPLIED = ROOT / "journal_catalog" / "core" / "core-additions-applied-2026-11-22.csv"
APPLIED_REVIEW = ROOT / "journal_catalog" / "core" / "core-review-applied-2026-11-22.csv"
BACKUP = ROOT / ".local" / "backups" / "core-review-apply-2026-11-22"

PACKAGES = {
    "custom_toc": {"package": "custom_toc_journals", "version": "2.4.0", "supplier": "官网",
                   "template_group": "custom_toc", "source_group": "custom_toc",
                   "data_source_detail": "官网当期目次（核心刊复核补录）"},
    "magetech": {"package": "magetech_journals", "version": "1.4.1", "supplier": "玛格泰克",
                 "template_group": "magetech", "source_group": "magetech",
                 "data_source_detail": "官网当期目次（核心刊复核补录）"},
    "qinyun": {"package": "qinyun_journals", "version": "1.0.6", "supplier": "勤云",
               "template_group": "qinyun", "source_group": "qinyun",
               "data_source_detail": "官网当期目次（核心刊复核补录）"},
    "vsb": {"package": "vsb_journals", "version": "1.2.2", "supplier": "VSB",
            "template_group": "vsb", "source_group": "vsb",
            "data_source_detail": "官网当期目次（核心刊复核补录）"},
}

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
    for salt in range(20):
        key = hashlib.sha1(f"{norm(name)}|{url}|{salt}".encode("utf-8")).hexdigest()[:16]
        if key not in used:
            used.add(key)
            return key
    raise RuntimeError("cannot allocate key")


def main():
    rows = [row for row in csv.DictReader(REVIEW.open(encoding="utf-8-sig")) if int(row.get("items") or 0) >= 2]
    BACKUP.mkdir(parents=True, exist_ok=True)
    for spec in PACKAGES.values():
        package = spec["package"]
        for filename in ("journals.json", "manifest.json"):
            source = ACADEMIC / package / filename
            if source.exists():
                shutil.copy2(source, BACKUP / f"{package}-{filename}")

    package_rows, used_keys, existing_names = {}, set(), {}
    for spec in PACKAGES.values():
        package = spec["package"]
        path = ACADEMIC / package / "journals.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        package_rows[package] = data if isinstance(data, list) else data.get("journals", [])
        for row in package_rows[package]:
            used_keys.add(row.get("journal_key"))
            existing_names.setdefault(package, set()).add(norm(row.get("name")))

    applied = []
    for row in rows:
        parser = row["parser"]
        if parser not in PACKAGES:
            continue
        spec = PACKAGES[parser]
        package = spec["package"]
        name = row["journal_name"]
        url = row["official_url"]
        if norm(name) in existing_names.get(package, set()):
            continue
        key = stable_key(name, url, used_keys)
        entry = {
            "journal_key": key, "name": name, "url": url, "current_url": row["current_url"],
            "supplier": spec["supplier"], "template_group": spec["template_group"],
            "evidence": "core_review_2026-11-22", "source_file": "",
            "catalog_source": "core_2026-11-22", "official_url": url,
            "data_source": "official_site", "data_source_detail": spec["data_source_detail"],
            "source_group": spec["source_group"], "status": "verified_current_issue",
            "verification_mode": "latest_issue", "verified_at": "2026-11-22",
            "probe_items": int(row["items"]), "probe_first_title": row["first_title"],
            "core_levels": row["core_levels"], "categories": row["categories"],
            "tags": [core_tag(row["core_levels"]), discipline_tag(row["categories"]), "采集:核心补录", "目录:核心"],
        }
        try:
            adapter = json.loads(row["adapter"] or "{}")
        except Exception:
            adapter = {}
        for field in ("article_link_regex", "link_base", "issue_link", "pair_link", "onclick_link", "json_api"):
            if adapter.get(field):
                entry[field] = adapter[field]
        package_rows[package].append(entry)
        existing_names.setdefault(package, set()).add(norm(name))
        applied.append({"journal_name": name, "journal_key": key, "target_package": package,
                        "items": row["items"], "first_title": row["first_title"],
                        "core_levels": row["core_levels"], "categories": row["categories"],
                        "official_url": url, "current_url": row["current_url"]})

    for package, rows_package in package_rows.items():
        path = ACADEMIC / package / "journals.json"
        path.write_text(json.dumps(rows_package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_path = ACADEMIC / package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for spec in PACKAGES.values():
            if spec["package"] == package:
                manifest["package_version"] = spec["version"]
        if package == "custom_toc_journals":
            manifest["description"] = f"读取自定义 CMS/静态当期目录 HTML 与公开 JSON/onclick/表格配对目次，收录 2377 目录中 {len(rows_package)} 本当期文章入口可解析的期刊"
            defaults = manifest["parameters_schema"]["properties"]["journal_keys"]["default"]
            for entry in rows_package:
                if entry["journal_key"] not in defaults:
                    defaults.append(entry["journal_key"])
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fields = ["journal_name", "journal_key", "target_package", "items", "first_title",
              "core_levels", "categories", "official_url", "current_url"]
    with APPLIED_REVIEW.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(applied)
    with APPLIED.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writerows(applied)
    print("applied", len(applied), Counter(row["target_package"] for row in applied))
    print("saved", APPLIED_REVIEW)


if __name__ == "__main__":
    main()