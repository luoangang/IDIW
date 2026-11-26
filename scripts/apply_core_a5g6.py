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
PLAN = ROOT / "journal_catalog" / "core" / "core-a5g6-candidates-2026-11-24.csv"
VERIFY = ROOT / ".local" / "core" / "probe-verify-a5g6-2026-11-24.csv"
OUTPUT = ROOT / "journal_catalog" / "core" / "core-a5g6-additions-applied-2026-11-24.csv"
BACKUP = ROOT / ".local" / "backups" / "core-a5g6-apply-2026-11-24" / "pre-apply"
DATE = "2026-11-24"
EVIDENCE = "core_2026-11-24_a5g6"
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")
PACKAGES = {
    "custom_toc_journals": ROOT / "crawler_packages" / "academic" / "custom_toc_journals",
    "qinyun_journals": ROOT / "crawler_packages" / "academic" / "qinyun_journals",
}
VERSIONS = {"custom_toc_journals": "3.6.0", "qinyun_journals": "1.6.0"}


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


def json_field(row, field):
    value = row.get(field) or ""
    return json.loads(value) if value else None


def main():
    rows = list(csv.DictReader(PLAN.open(encoding="utf-8-sig")))
    verify = {row["journal_name"]: row for row in csv.DictReader(VERIFY.open(encoding="utf-8-sig"))}
    BACKUP.mkdir(parents=True, exist_ok=True)
    for package in PACKAGES.values():
        for filename in ("journals.json", "manifest.json", "crawler.py"):
            shutil.copy2(package / filename, BACKUP / f"{package.name}-{filename}")

    applied, skipped = [], []
    by_package = {}
    for row in rows:
        target = row["target_package"]
        package = PACKAGES[target]
        if target not in by_package:
            journals = json.loads((package / "journals.json").read_text(encoding="utf-8"))
            by_package[target] = {
                "journals": journals,
                "used_keys": {entry.get("journal_key") for entry in journals},
                "names": {norm(entry.get("name")) for entry in journals},
            }
        state = by_package[target]
        name = row["journal_name"]
        if norm(name) in state["names"]:
            skipped.append((name, target, "duplicate name"))
            continue
        result = verify.get(name, {})
        items = int(float(result.get("items") or 0))
        first_title = result.get("first_title") or row.get("expected_first_title", "")
        url = row.get("official_url") or row.get("current_url") or ""
        key = stable_key(name, url, state["used_keys"])
        tags = [
            core_tag(row.get("core_levels")),
            discipline_tag(row.get("categories")),
            "采集:官网当期目次",
            "当期核验",
            "目录:核心",
        ]
        entry = {
            "journal_key": key,
            "name": name,
            "url": url,
            "current_url": row.get("current_url", ""),
            "supplier": "勤云" if target == "qinyun_journals" else "官网",
            "template_group": "qinyun" if target == "qinyun_journals" else "custom_toc",
            "evidence": EVIDENCE,
            "source_file": "",
            "catalog_source": "core_2026-11-24",
            "official_url": url,
            "data_source": row.get("data_source") or "official_site",
            "data_source_detail": row.get("data_source_detail", ""),
            "source_group": "qinyun" if target == "qinyun_journals" else "custom_toc",
            "status": "verified_current_issue",
            "verification_mode": "latest_issue",
            "verified_at": DATE,
            "probe_items": items,
            "probe_first_title": first_title,
            "core_levels": row.get("core_levels", ""),
            "categories": row.get("categories", ""),
            "tags": tags,
        }
        if target == "qinyun_journals":
            entry["url_signature"] = None
        if row.get("article_link_regex"):
            entry["article_link_regex"] = row["article_link_regex"]
        if row.get("link_base"):
            entry["link_base"] = row["link_base"]
        if str(row.get("relaxed_title_filter", "")).lower() == "true":
            entry["relaxed_title_filter"] = True
        for field in ("section_start_regex", "section_end_regex", "last_section_regex"):
            if row.get(field):
                entry[field] = row[field]
        pair_link = json_field(row, "pair_link")
        if pair_link:
            entry["pair_link"] = pair_link
        pagination = json_field(row, "pagination")
        if pagination:
            entry["pagination"] = pagination
        if row.get("max_response_bytes"):
            entry["max_response_bytes"] = int(float(row["max_response_bytes"]))
        state["journals"].append(entry)
        state["names"].add(norm(name))
        applied.append({
            "journal_name": name, "journal_key": key, "target_package": target,
            "items": items, "first_title": first_title,
            "core_levels": row.get("core_levels", ""), "categories": row.get("categories", ""),
            "official_url": url, "current_url": row.get("current_url", ""),
            "data_source": entry["data_source"], "article_link_regex": entry.get("article_link_regex", ""),
            "pair_link": json.dumps(entry.get("pair_link"), ensure_ascii=False) if entry.get("pair_link") else "",
        })

    for target, state in by_package.items():
        package = PACKAGES[target]
        journals = state["journals"]
        (package / "journals.json").write_text(json.dumps(journals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["package_version"] = VERSIONS[target]
        prop = manifest["parameters_schema"]["properties"]["journal_keys"]
        prop["maxItems"] = max(int(prop.get("maxItems", 30)), len(journals) + 10)
        default = prop["default"]
        for row in applied:
            if row["target_package"] == target and row["journal_key"] not in default:
                default.append(row["journal_key"])
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(target, "catalog", len(journals), "version", manifest["package_version"], "maxItems", prop["maxItems"])

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
