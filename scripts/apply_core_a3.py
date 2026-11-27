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
PACKAGE = ROOT / "crawler_packages" / "academic" / "custom_toc_journals"
PLAN = ROOT / "journal_catalog" / "core" / "core-a3-additions-ready-2026-11-24.csv"
BACKUP = ROOT / ".local" / "backups" / "core-a3-apply-2026-11-24"
OUTPUT = ROOT / "journal_catalog" / "core" / "core-a3-additions-applied-2026-11-24.csv"
VERSION = "3.4.0"
DATE = "2026-11-24"
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
    for filename in ("journals.json", "manifest.json"):
        shutil.copy2(PACKAGE / filename, BACKUP / f"custom_toc_journals-{filename}")

    journals_path = PACKAGE / "journals.json"
    journals = json.loads(journals_path.read_text(encoding="utf-8"))
    used_keys = {row.get("journal_key") for row in journals}
    existing_names = {norm(row.get("name")) for row in journals}

    applied, skipped = [], []
    for row in rows:
        name = row["journal_name"]
        if norm(name) in existing_names:
            skipped.append((name, "duplicate name"))
            continue
        url = row.get("official_url") or row.get("current_url") or ""
        key = stable_key(name, url, used_keys)
        public = row.get("data_source") == "public_platform"
        tags = [
            core_tag(row.get("core_levels")),
            discipline_tag(row.get("categories")),
            "采集:公开平台" if public else "采集:官网当期目次",
            "当期核验",
            "目录:核心",
        ]
        if public:
            tags.insert(3, "非官网")
        entry = {
            "journal_key": key,
            "name": name,
            "url": url,
            "current_url": row.get("current_url", ""),
            "supplier": "公开平台" if public else "官网",
            "template_group": "custom_toc",
            "evidence": "core_2026-11-24",
            "source_file": "",
            "catalog_source": "core_2026-11-24",
            "official_url": url,
            "data_source": row.get("data_source", "official_site"),
            "data_source_detail": row.get("data_source_detail", "官网当期目次 HTML（核心刊补录）"),
            "source_group": "custom_toc",
            "status": "verified_current_issue",
            "verification_mode": "latest_issue",
            "verified_at": DATE,
            "probe_items": int(float(row.get("items") or 0)),
            "probe_first_title": row.get("first_title", ""),
            "core_levels": row.get("core_levels", ""),
            "categories": row.get("categories", ""),
            "tags": tags,
        }
        if row.get("article_link_regex"):
            entry["article_link_regex"] = row["article_link_regex"]
        if row.get("link_base"):
            entry["link_base"] = row["link_base"]
        if str(row.get("relaxed_title_filter", "")).lower() == "true":
            entry["relaxed_title_filter"] = True
        journals.append(entry)
        existing_names.add(norm(name))
        applied.append({
            "journal_name": name, "journal_key": key, "target_package": "custom_toc_journals",
            "items": row.get("items", ""), "first_title": row.get("first_title", ""),
            "core_levels": row.get("core_levels", ""), "categories": row.get("categories", ""),
            "official_url": url, "current_url": row.get("current_url", ""),
            "data_source": entry["data_source"], "article_link_regex": entry.get("article_link_regex", ""),
        })

    journals_path.write_text(json.dumps(journals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = PACKAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package_version"] = VERSION
    prop = manifest["parameters_schema"]["properties"]["journal_keys"]
    prop["maxItems"] = max(int(prop.get("maxItems", 500)), len(journals) + 10)
    default = prop["default"]
    for row in applied:
        if row["journal_key"] not in default:
            default.append(row["journal_key"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(applied[0].keys()) if applied else ["journal_name"])
        writer.writeheader()
        writer.writerows(applied)
    print("applied", len(applied), Counter(row["data_source"] for row in applied))
    print("skipped", len(skipped), skipped)
    print("catalog now", len(journals), "maxItems", prop["maxItems"])
    print("saved", OUTPUT)
    print("backup", BACKUP)


if __name__ == "__main__":
    raise SystemExit(main())
