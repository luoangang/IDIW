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
ACCEPTED = ROOT / "journal_catalog" / "core" / "workbuddy" / "accepted-workbuddy-2026-11-25.csv"
VERIFIED = ROOT / ".local" / "accept" / "verified-known.csv"
OUTPUT = ROOT / "journal_catalog" / "core" / "workbuddy" / "accepted-known-applied-2026-11-25.csv"
BACKUP = ROOT / ".local" / "backups" / "workbuddy-accepted-known-apply-2026-11-25"
DATE = "2026-11-25"
EVIDENCE = "workbuddy_accepted_2026-11-25"
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")
VERSIONS = {
    "magetech_journals": "1.16.1",
    "qinyun_journals": "1.9.1",
    "rhzh_journals": "1.3.1",
    "founder_journals": "1.2.1",
    "cnki_cbpt": "1.12.0",
    "paperonce_journals": "1.1.1",
}
SUPPLIERS = {
    "magetech_journals": "玛格泰克",
    "qinyun_journals": "勤云",
    "rhzh_journals": "仁和汇智",
    "founder_journals": "北大方正",
    "cnki_cbpt": "同方知网",
    "paperonce_journals": "PaperOnce",
}
GROUPS = {
    "magetech_journals": "magetech",
    "qinyun_journals": "qinyun",
    "rhzh_journals": "rhzh",
    "founder_journals": "founder",
    "cnki_cbpt": "cnki_cbpt",
    "paperonce_journals": "paperonce",
}
URL_OVERRIDES = {
    "临床心血管病杂志": "https://lcxxg.whuhzzs.com/data/article/current-data?publisherId=lcxxg",
    "临床急诊杂志": "https://lcjz.whuhzzs.com/data/article/current-data?publisherId=lcjz",
    "临床泌尿外科杂志": "https://lcmw.whuhzzs.com/data/article/current-data?publisherId=lcmw",
    "临床血液学杂志": "https://lcxy.whuhzzs.com/data/article/current-data?publisherId=lcxy",
    "兵工自动化": "http://bgzdh.ijournals.com.cn/bgzdh/article/issue/2026_10",
    "玉米科学": "http://www.ymkx.com.cn/jms/issue/current",
    "农业机械学报": "https://www.j-csam.org/jcsam/article/issue/2026_23",
    "军事护理": "https://jfjhlzz.smmu.edu.cn/jfjhlzz/article/issue/2026_43_10",
    "农学学报": "http://nxxb.caass.org.cn/CN/2095-4050/current.shtml",
}
TARGET_OVERRIDES = {
    "玉米科学": "qinyun_journals",
}
BASE_OVERRIDES = {
    "断块油气田": "https://dkyqt.paperonce.org",
}
EXTRA_NAMES = {
    "临床心血管病杂志", "临床急诊杂志", "临床泌尿外科杂志", "临床血液学杂志", "兵工自动化",
    "四川大学学报. 自然科学版", "新疆石油地质", "测试技术学报", "电焊机",
    "玉米科学", "农业机械学报", "南京信息工程大学学报自然科学版", "军事护理",
    "现代检验医学杂志", "断块油气田", "现代应用物理", "耐火材料", "农学学报",
}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def norm(value):
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(value or "")).lower())


def stable_key(name, url, used):
    for salt in range(100):
        key = hashlib.sha1(f"{norm(name)}|{url}|{salt}".encode("utf-8")).hexdigest()[:16]
        if key not in used:
            used.add(key)
            return key
    raise RuntimeError("cannot allocate journal key")


def origin(value):
    parts = urlsplit(value or "")
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def metadata_map():
    files = [
        ROOT / "journal_catalog" / "core" / "workbuddy" / "b-held-2026-11-24.csv",
        ROOT / "journal_catalog" / "core" / "c-group" / "c-group-main-2026-11-24.csv",
        ROOT / "journal_catalog" / "core" / "c-group" / "c-group-main-salvage-2026-11-24.csv",
        ROOT / "journal_catalog" / "core" / "c-group" / "c-group-workbuddy-2026-11-24.csv",
        ROOT / "journal_catalog" / "core" / "ambiguous-2026-11-24.csv",
    ]
    result = {}
    for path in files:
        for row in read_csv(path):
            name = row.get("journal_name", "").strip()
            if name and name not in result:
                result[name] = row
    return result


def founder_fields(row):
    note = row.get("note") or ""
    site_id = re.search(r"site_id=(\d+)", note)
    publication_id = re.search(r"publication_index_id=(\d+)", note)
    base_url = re.search(r"base_url=([^；;\s]+)", note)
    api = row.get("json_api") or row.get("current_url") or ""
    if not site_id:
        site_id = re.search(r"[?&]siteId=(\d+)", api)
    if not base_url:
        base_url = None
    base = (base_url.group(1).rstrip("/") if base_url else origin(api) or row.get("official_url", ""))
    return {
        "base_url": base,
        "site_id": int(site_id.group(1)) if site_id else None,
        "publication_index_id": int(publication_id.group(1)) if publication_id else None,
    }


def build_entry(row, meta, key):
    target = TARGET_OVERRIDES.get(row["journal_name"], row["target_package"])
    name = row["journal_name"]
    current_url = URL_OVERRIDES.get(name) or row.get("current_url") or row.get("candidate_url") or ""
    official_url = BASE_OVERRIDES.get(name) or (meta.get("official_url") or "").strip() or origin(current_url) or row.get("candidate_url", "")
    source_type = row.get("source_type") or "official_site"
    items = int(float(row.get("items") or 0))
    entry = {
        "journal_key": key,
        "name": name,
        "url": official_url or origin(current_url),
        "supplier": SUPPLIERS[target],
        "template_group": GROUPS[target],
        "evidence": EVIDENCE,
        "source_file": ACCEPTED.name,
        "catalog_source": "core_2026-11-25",
        "official_url": official_url,
        "data_source": source_type,
        "data_source_detail": "WorkBuddy 证据 + 主线程 parser live 复核",
        "source_group": GROUPS[target],
        "status": "verified_current_issue",
        "verification_mode": "latest_issue",
        "verified_at": DATE,
        "probe_items": items,
        "probe_first_title": row.get("first_title", ""),
        "core_levels": meta.get("core_levels", ""),
        "categories": meta.get("categories", ""),
        "tags": [SUPPLIERS[target], f"采集:{'API' if source_type == 'official_api' else '官网目次'}", "目录:核心", "当期核验"],
    }
    host = (urlsplit(official_url or current_url).hostname or "").lower()
    if target == "cnki_cbpt":
        host = (urlsplit(row.get("current_url") or official_url).hostname or "").lower()
        entry["url"] = "https://" + host
        entry["source_row"] = None
        entry["url_signature"] = "cbpt.cnki.net"
        entry["current_url"] = row.get("current_url", "")
    else:
        entry["current_url"] = current_url
        entry["url_signature"] = host or None
    if target == "founder_journals":
        fields = founder_fields(row)
        entry["base_url"] = fields["base_url"]
        entry["site_id"] = fields["site_id"]
        if fields["publication_index_id"]:
            entry["publication_index_id"] = fields["publication_index_id"]
        entry["official_url"] = fields["base_url"]
        entry["url"] = fields["base_url"]
    if target == "rhzh_journals" and "current-data" in current_url:
        entry["data_source"] = "official_api"
        entry["data_source_detail"] = "RHZH current-data 公开 JSON（查询参数 publisherId）"
    return entry


def main():
    accepted = {row["journal_name"]: row for row in read_csv(ACCEPTED)}
    verified = read_csv(VERIFIED)
    selected = [row for row in verified if row["status"] == "pass"]
    selected_names = {row["journal_name"] for row in selected} | EXTRA_NAMES
    rows = []
    for name in selected_names:
        row = accepted.get(name)
        if row is None:
            raise RuntimeError(f"selected journal missing from accepted CSV: {name}")
        rows.append(row)
    rows.sort(key=lambda row: (row["target_package"], row["journal_name"]))

    meta = metadata_map()
    missing_meta = [row["journal_name"] for row in rows if row["journal_name"] not in meta]
    if missing_meta:
        raise RuntimeError(f"missing core metadata: {missing_meta}")

    BACKUP.mkdir(parents=True, exist_ok=True)
    packages = {}
    for target in VERSIONS:
        path = ACADEMIC / target
        for filename in ("journals.json", "manifest.json"):
            shutil.copy2(path / filename, BACKUP / f"{target}-{filename}")
        journals = json.loads((path / "journals.json").read_text(encoding="utf-8"))
        packages[target] = {
            "path": path,
            "journals": journals,
            "used": {row.get("journal_key") for row in journals},
            "names": {norm(row.get("name")) for row in journals},
        }

    applied, skipped = [], []
    for row in rows:
        target = TARGET_OVERRIDES.get(row["journal_name"], row["target_package"])
        if target not in packages:
            skipped.append((row["journal_name"], f"unsupported package {target}"))
            continue
        state = packages[target]
        name = row["journal_name"]
        if norm(name) in state["names"]:
            skipped.append((name, "duplicate name"))
            continue
        url_for_key = (meta[name].get("official_url") or row.get("current_url") or "").strip()
        key = stable_key(name, url_for_key, state["used"])
        entry = build_entry(row, meta[name], key)
        if target == "founder_journals" and not entry.get("site_id"):
            skipped.append((name, "missing founder site_id"))
            continue
        state["journals"].append(entry)
        state["names"].add(norm(name))
        applied.append({
            "journal_name": name,
            "journal_key": key,
            "target_package": target,
            "items": row.get("items", ""),
            "first_title": row.get("first_title", ""),
            "core_levels": entry["core_levels"],
            "categories": entry["categories"],
            "official_url": entry["official_url"],
            "current_url": entry.get("current_url", ""),
            "data_source": entry["data_source"],
        })

    for target, state in packages.items():
        package = state["path"]
        package_rows = state["journals"]
        (package / "journals.json").write_text(
            json.dumps(package_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["package_version"] = VERSIONS[target]
        prop = manifest["parameters_schema"]["properties"]["journal_keys"]
        default = prop["default"]
        for row in applied:
            if row["target_package"] == target and row["journal_key"] not in default:
                default.append(row["journal_key"])
        prop["maxItems"] = max(int(prop.get("maxItems", 30)), len(default))
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(target, "catalog", len(package_rows), "version", manifest["package_version"],
              "maxItems", prop["maxItems"], "default", len(default))

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(applied[0].keys()) if applied else ["journal_name"])
        writer.writeheader()
        writer.writerows(applied)
    print("selected", len(rows), "applied", len(applied), Counter(row["target_package"] for row in applied))
    print("skipped", len(skipped), skipped)
    print("saved", OUTPUT)
    print("backup", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
