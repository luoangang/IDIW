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
PLAN = ROOT / "journal_catalog" / "core" / "core-social4-additions-ready-2026-11-23.csv"
BACKUP = ROOT / ".local" / "backups" / "core-social4-apply-2026-11-23"

PACKAGE_META = {
    "cnki_cbpt": {"version": "1.8.0", "supplier": "同方知网", "template_group": "cnki_cbpt",
                  "source_group": "cnki_cbpt", "data_source_detail": "CBPT/WKD 公开当期（核心刊补录）"},
    "magetech_journals": {"version": "1.10.0", "supplier": "玛格泰克", "template_group": "magetech",
                          "source_group": "magetech", "data_source_detail": "官网当期目次（核心刊补录）"},
    "qinyun_journals": {"version": "1.3.0", "supplier": "勤云", "template_group": "qinyun",
                        "source_group": "qinyun", "data_source_detail": "官网当期目次（核心刊补录）"},
    "rhzh_journals": {"version": "1.0.17", "supplier": "仁和汇智", "template_group": "rhzh",
                      "source_group": "rhzh", "data_source_detail": "官网当期目次（核心刊补录）"},
    "custom_toc_journals": {"version": "3.0.0", "supplier": "官网", "template_group": "custom_toc",
                            "source_group": "custom_toc", "data_source_detail": "官网当期目次（核心刊补录）"},
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
        raw = f"{norm(name)}|{url}|{salt}"
        key = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        if key not in used:
            used.add(key)
            return key
    raise RuntimeError("cannot allocate journal key")


def main():
    rows = list(csv.DictReader(PLAN.open(encoding="utf-8-sig")))
    BACKUP.mkdir(parents=True, exist_ok=True)
    for package in PACKAGE_META:
        for filename in ("journals.json", "manifest.json"):
            source = ACADEMIC / package / filename
            if source.exists():
                shutil.copy2(source, BACKUP / f"{package}-{filename}")

    package_rows = {}
    used_keys = set()
    existing_names = {}
    for package in PACKAGE_META:
        path = ACADEMIC / package / "journals.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        package_rows[package] = data if isinstance(data, list) else data.get("journals", [])
        for row in package_rows[package]:
            used_keys.add(row.get("journal_key"))
            existing_names.setdefault(package, set()).add(norm(row.get("name")))

    applied, skipped = [], []
    for row in rows:
        package = row["target_package"]
        if package not in PACKAGE_META:
            skipped.append((row["journal_name"], "unknown package"))
            continue
        name = row["journal_name"]
        url = row["official_url"]
        if norm(name) in existing_names.get(package, set()):
            skipped.append((name, "duplicate name"))
            continue
        key = stable_key(name, url, used_keys)
        meta = PACKAGE_META[package]
        tags = [core_tag(row["core_levels"]), discipline_tag(row["categories"]), "采集:核心补录", "目录:核心"]
        entry = {
            "journal_key": key,
            "name": name,
            "url": url,
            "current_url": row["current_url"],
            "supplier": meta["supplier"],
            "template_group": meta["template_group"],
            "evidence": "core_2026-11-22",
            "source_file": "",
            "catalog_source": "core_2026-11-22",
            "official_url": url,
            "data_source": "official_site",
            "data_source_detail": meta["data_source_detail"],
            "source_group": meta["source_group"],
            "status": "verified_current_issue",
            "verification_mode": "latest_issue",
            "verified_at": "2026-11-22",
            "probe_items": int(row["items"]),
            "probe_first_title": row["first_title"],
            "core_levels": row["core_levels"],
            "categories": row["categories"],
            "tags": tags,
        }
        if package == "cnki_cbpt":
            host = (urlsplit(url).hostname or "").lower()
            entry["source_row"] = None
            entry["url"] = "https://" + host
            entry["url_signature"] = "cbpt.cnki.net"
            entry["data_source_detail"] = meta["data_source_detail"]
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
        manifest["package_version"] = PACKAGE_META[package]["version"]
        if package == "custom_toc_journals":
            manifest["description"] = f"读取自定义 CMS/静态当期目录 HTML 与公开 JSON/onclick/表格配对目次，收录 2377 目录中 {len(rows_package)} 本当期文章入口可解析的期刊"
            prop = manifest["parameters_schema"]["properties"]["journal_keys"]
            prop["maxItems"] = max(int(prop.get("maxItems", 500)), len(rows_package) + 10)
            defaults = prop["default"]
            for entry in rows_package:
                if entry["journal_key"] not in defaults:
                    defaults.append(entry["journal_key"])
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output = ROOT / "journal_catalog" / "core" / "core-social4-additions-applied-2026-11-23.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(applied[0].keys()) if applied else ["journal_name"])
        writer.writeheader()
        writer.writerows(applied)
    print("applied", len(applied), Counter(row["target_package"] for row in applied))
    print("skipped", len(skipped))
    for row in skipped[:20]:
        print(" skip", row)
    print("saved", output)
    print("backup", BACKUP)


if __name__ == "__main__":
    raise SystemExit(main())