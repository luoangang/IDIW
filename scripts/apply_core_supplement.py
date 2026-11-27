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
PACKAGE = ROOT / "crawler_packages" / "academic" / "supplement_journals"
PLAN = ROOT / "journal_catalog" / "core" / "core-supplement-additions-ready-2026-11-24.csv"
BACKUP = ROOT / ".local" / "backups" / "core-supplement-apply-2026-11-24"
OUTPUT = ROOT / "journal_catalog" / "core" / "core-supplement-additions-applied-2026-11-24.csv"
VERSION = "1.1.0"
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


def format_issn(value):
    text = str(value or "").strip().upper().replace(" ", "")
    digits = text.replace("-", "")
    if len(digits) == 8:
        return digits[:4] + "-" + digits[4:]
    return text


def main():
    rows = list(csv.DictReader(PLAN.open(encoding="utf-8-sig")))
    BACKUP.mkdir(parents=True, exist_ok=True)
    for filename in ("journals.json", "manifest.json"):
        shutil.copy2(PACKAGE / filename, BACKUP / f"supplement_journals-{filename}")

    journals_path = PACKAGE / "journals.json"
    journals = json.loads(journals_path.read_text(encoding="utf-8"))
    used_keys = {row.get("journal_key") for row in journals}
    existing_names = {norm(row.get("name")) for row in journals}
    existing_issns = set()
    for row in journals:
        for issn in (row.get("issns") or [row.get("issn")]):
            if issn:
                existing_issns.add(norm(issn).replace("-", ""))

    applied, skipped = [], []
    for row in rows:
        issns = [format_issn(value) for value in str(row.get("issns") or "").split(";") if value.strip()]
        if not issns:
            skipped.append((row.get("journal_name"), "no issn"))
            continue
        if any(len(value.replace("-", "")) != 8 for value in issns):
            skipped.append((row.get("journal_name"), "invalid issn"))
            continue
        if norm(row["journal_name"]) in existing_names:
            skipped.append((row["journal_name"], "duplicate name"))
            continue
        if any(norm(issn).replace("-", "") in existing_issns for issn in issns):
            skipped.append((row["journal_name"], "duplicate issn"))
            continue
        url = row.get("official_url") or f"https://search.crossref.org/?q={issns[0].replace('-', '')}"
        key = stable_key(row["journal_name"], url, used_keys)
        publisher = row.get("platform") or "OpenAlex/Crossref"
        entry = {
            "journal_key": key,
            "name": row["journal_name"],
            "name_en": row.get("name_en") or row["journal_name"],
            "issn": issns[0],
            "issns": issns,
            "publisher": publisher,
            "url": url,
            "tags": [
                core_tag(row.get("core_levels")),
                discipline_tag(row.get("categories")),
                "采集:OpenAlex/Crossref",
                "非官网",
                "目录:核心",
            ],
            "source_system": "openalex_crossref",
            "status": "verified",
            "catalog_source": "core_2026-11-24",
            "official_url": url,
            "data_source": "openalex_crossref",
            "data_source_detail": "OpenAlex/Crossref API（非官网页面）",
            "data_source_url": "https://api.openalex.org/works; https://api.crossref.org/works",
            "core_levels": row.get("core_levels", ""),
            "categories": row.get("categories", ""),
            "language": "英文",
            "verification_mode": "api_sample",
            "verified_at": DATE,
        }
        journals.append(entry)
        existing_names.add(norm(entry["name"]))
        for issn in issns:
            existing_issns.add(norm(issn).replace("-", ""))
        applied.append({
            "journal_name": entry["name"],
            "journal_key": key,
            "target_package": "supplement_journals",
            "issns": ";".join(issns),
            "core_levels": entry["core_levels"],
            "categories": entry["categories"],
            "official_url": url,
            "publisher": publisher,
        })

    journals_path.write_text(json.dumps(journals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = PACKAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package_version"] = VERSION
    prop = manifest["parameters_schema"]["properties"]["journal_keys"]
    prop["maxItems"] = max(int(prop.get("maxItems", 100)), len(journals) + 20)
    defaults = prop["default"]
    for row in applied:
        if row["journal_key"] not in defaults:
            defaults.append(row["journal_key"])
    manifest["description"] = (
        "读取 OpenAlex/Crossref 公开 API 获取期刊最近文章元数据；"
        "收录核心/2377 目录中官网不可达或仅英文出版的期刊，来源明确标注非官网。"
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(applied[0].keys()) if applied else ["journal_name"])
        writer.writeheader()
        writer.writerows(applied)
    print("applied", len(applied), Counter(row["publisher"] for row in applied).most_common(10))
    print("skipped", len(skipped), skipped[:10])
    print("catalog now", len(journals), "maxItems", prop["maxItems"])
    print("saved", OUTPUT)
    print("backup", BACKUP)


if __name__ == "__main__":
    raise SystemExit(main())
