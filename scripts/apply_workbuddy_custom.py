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
PACKAGE = ROOT / "crawler_packages" / "academic" / "custom_toc_journals"
ACCEPTED = ROOT / "journal_catalog" / "core" / "workbuddy" / "accepted-workbuddy-2026-11-25.csv"
CONFIGS = ROOT / ".local" / "accept" / "custom-adapter-configs.csv"
VERIFIED = ROOT / ".local" / "accept" / "verified-custom.csv"
OUTPUT = ROOT / "journal_catalog" / "core" / "workbuddy" / "custom-applied-2026-11-25.csv"
BACKUP = ROOT / ".local" / "backups" / "workbuddy-custom-apply-2026-11-25"
VERSION = "3.10.1"
DATE = "2026-11-25"
EVIDENCE = "workbuddy_custom_2026-11-25"
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")
RELAXED = {
    "水力发电学报", "浙江大学学报. 工学版", "海军工程大学学报", "水力发电",
    "情报杂志", "探测与控制学报", "临床神经外科杂志", "天然气工业",
    "仪表技术与传感器", "应用与环境生物学报",
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


def load_meta():
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


def parse_json(value):
    if not value:
        return None
    try:
        obj = json.loads(value)
        return obj if isinstance(obj, dict) else None
    except (TypeError, ValueError):
        return None


def normalize_latest_url(value):
    return re.sub(r"(LastIssueList\?[^\"'\s]*?IssueId=)\d+", r"\g<1>0", value or "", flags=re.I)


def build_entry(name, accepted, config, meta, key):
    current_url = (config.get("current_url") or accepted.get("current_url") or accepted.get("candidate_url") or "").strip()
    if not current_url:
        raise RuntimeError(f"missing current_url for {name}")
    official_url = (meta.get("official_url") or "").strip() or origin(current_url) or current_url
    json_api = parse_json(config.get("json_api")) or parse_json(accepted.get("json_api"))
    if json_api and json_api.get("url"):
        json_api["url"] = normalize_latest_url(json_api["url"])
    pair_link = parse_json(config.get("pair_link")) or parse_json(accepted.get("pair_link"))
    onclick_link = parse_json(config.get("onclick_link")) or parse_json(accepted.get("onclick_link"))
    section = parse_json(config.get("section_regex")) or parse_json(accepted.get("section_regex")) or {}
    items = int(float(config.get("items") or accepted.get("items") or 0))
    entry = {
        "journal_key": key,
        "name": name,
        "url": official_url,
        "current_url": current_url,
        "supplier": "官网",
        "template_group": "custom_toc",
        "evidence": EVIDENCE,
        "source_file": "custom-adapter-configs-2026-11-25.csv",
        "catalog_source": "core_2026-11-25",
        "official_url": official_url,
        "data_source": accepted.get("source_type") or "official_site",
        "data_source_detail": "WorkBuddy 证据 + 主线程/适配 agent live 复核",
        "source_group": "custom_toc",
        "status": "verified_current_issue",
        "verification_mode": "latest_issue",
        "verified_at": DATE,
        "probe_items": items,
        "probe_first_title": config.get("first_title") or accepted.get("first_title") or "",
        "core_levels": meta.get("core_levels", ""),
        "categories": meta.get("categories", ""),
        "tags": ["官网", "采集:官网目次", "目录:核心", "当期核验"],
        "url_signature": (urlsplit(official_url).hostname or "").lower() or None,
    }
    for field, value in (("json_api", json_api), ("pair_link", pair_link), ("onclick_link", onclick_link)):
        if value:
            entry[field] = value
    regex = config.get("article_link_regex") or accepted.get("article_link_regex")
    if regex:
        entry["article_link_regex"] = regex
    link_base = config.get("link_base") or accepted.get("link_base")
    if link_base:
        entry["link_base"] = link_base
    for key_name, source in (("section_start_regex", "start"), ("section_end_regex", "end"), ("last_section_regex", "last")):
        if section.get(source):
            entry[key_name] = section[source]
        elif accepted.get(key_name):
            entry[key_name] = accepted[key_name]
    if name in RELAXED or "relaxed_title_filter=true" in (config.get("note") or ""):
        entry["relaxed_title_filter"] = True
    return entry


def main():
    accepted = {row["journal_name"]: row for row in read_csv(ACCEPTED)}
    configs = {row["journal_name"]: row for row in read_csv(CONFIGS)}
    verified = read_csv(VERIFIED)
    selected = {row["journal_name"] for row in verified if row["status"] in {"pass", "warn"}}
    selected |= {name for name, row in configs.items() if row.get("status") in {"pass", "warn"}}
    rows = []
    for name in selected:
        config = configs.get(name, {})
        source = accepted.get(name, {})
        rows.append((name, source, config))
    rows.sort(key=lambda item: item[0])

    meta = load_meta()
    missing = [name for name, _, _ in rows if name not in meta]
    if missing:
        raise RuntimeError(f"missing core metadata: {missing}")

    journals = json.loads((PACKAGE / "journals.json").read_text(encoding="utf-8"))
    used = {row.get("journal_key") for row in journals}
    names = {norm(row.get("name")) for row in journals}
    BACKUP.mkdir(parents=True, exist_ok=True)
    for filename in ("journals.json", "manifest.json"):
        shutil.copy2(PACKAGE / filename, BACKUP / filename)

    applied, skipped = [], []
    for name, accepted_row, config in rows:
        if norm(name) in names:
            skipped.append((name, "duplicate name"))
            continue
        meta_row = meta[name]
        key = stable_key(name, meta_row.get("official_url") or config.get("current_url") or accepted_row.get("current_url", ""), used)
        entry = build_entry(name, accepted_row, config, meta_row, key)
        journals.append(entry)
        names.add(norm(name))
        applied.append({
            "journal_name": name,
            "journal_key": key,
            "target_package": "custom_toc_journals",
            "items": entry["probe_items"],
            "first_title": entry["probe_first_title"],
            "core_levels": entry["core_levels"],
            "categories": entry["categories"],
            "official_url": entry["official_url"],
            "current_url": entry["current_url"],
            "data_source": entry["data_source"],
            "mode": "json" if entry.get("json_api") else "pair" if entry.get("pair_link") else "onclick" if entry.get("onclick_link") else "regex",
        })

    (PACKAGE / "journals.json").write_text(json.dumps(journals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = PACKAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package_version"] = VERSION
    prop = manifest["parameters_schema"]["properties"]["journal_keys"]
    default = prop["default"]
    for row in applied:
        if row["journal_key"] not in default:
            default.append(row["journal_key"])
    prop["maxItems"] = max(int(prop.get("maxItems", 30)), len(default))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(applied[0].keys()) if applied else ["journal_name"])
        writer.writeheader()
        writer.writerows(applied)
    print("catalog", len(journals), "version", manifest["package_version"], "maxItems", prop["maxItems"], "default", len(default))
    print("selected", len(rows), "applied", len(applied), Counter(row["mode"] for row in applied))
    print("skipped", len(skipped), skipped)
    print("saved", OUTPUT)
    print("backup", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
