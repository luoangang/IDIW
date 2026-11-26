from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPLEMENT = ROOT / "crawler_packages" / "academic" / "supplement_journals" / "journals.json"
OUT_DIR = ROOT / "journal_catalog" / "foreign"
WATCHLIST = OUT_DIR / "foreign_journals_seed_2026-11-25.csv"
SAMPLE = OUT_DIR / "foreign_source_audit_sample_2026-11-25.csv"
DATE = "2026-11-25"
FLAGSHIP = [
    ("Nature", "0028-0836", "Nature Portfolio / Springer Nature", "https://www.nature.com/nature"),
    ("Science", "0036-8075", "AAAS", "https://www.science.org/journal/science"),
    ("Proceedings of the National Academy of Sciences", "0027-8424", "National Academy of Sciences", "https://www.pnas.org"),
    ("Cell", "0092-8674", "Cell Press / Elsevier", "https://www.cell.com/cell"),
]
GROUPS = [
    ("springer", ("springer",)),
    ("elsevier", ("elsevier",)),
    ("wiley", ("wiley",)),
    ("nature", ("nature",)),
    ("university_press", ("oxford", "oup", "cambridge", "bmj", "taylor", "sage", "iop", "aaas", "wolters", "lww", "ovid", "american", "annual", "plos", "frontiers", "acs", "rsc", "aps", "ieee")),
    ("china_platform", ("keai", "sciopen", "sciengine", "magtech", "magetech", "rhzh", "founder", "custom")),
]
QUOTAS = {"springer": 40, "elsevier": 35, "wiley": 12, "nature": 5, "university_press": 20, "china_platform": 26, "other": 8}


def normalize_issn(value: str) -> str:
    match = re.search(r"(\d{4})-?(\d{3}[\dXx])", value or "")
    return f"{match.group(1)}-{match.group(2).upper()}" if match else ""


def title_norm(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def journal_id(issn: str, title: str) -> str:
    return hashlib.sha1(f"{issn}|{title}".encode("utf-8")).hexdigest()[:16]


def group_of(publisher: str) -> str:
    value = (publisher or "").lower()
    for name, needles in GROUPS:
        if any(needle in value for needle in needles):
            return name
    return "other"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    journals = json.loads(SUPPLEMENT.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for journal in journals:
        title = (journal.get("name_en") or journal.get("name") or "").strip()
        title_zh = (journal.get("name") or "").strip()
        issns = [normalize_issn(value) for value in journal.get("issns") or [journal.get("issn")]]
        issns = list(dict.fromkeys(value for value in issns if value))
        issn = issns[0] if issns else ""
        tags = journal.get("tags") or []
        subjects = [tag[3:] for tag in tags if tag.startswith("学科:")]
        levels = [tag[3:] for tag in tags if tag.startswith("核心:")]
        publisher = journal.get("publisher") or ""
        rows.append({
            "journal_id": journal_id(issn, title),
            "title": title,
            "title_zh": title_zh if title_zh != title else "",
            "title_norm": title_norm(title),
            "issn": issn,
            "eissn": issns[1] if len(issns) > 1 else "",
            "issns": "; ".join(issns),
            "publisher": publisher,
            "publisher_group": group_of(publisher),
            "subject": "; ".join(subjects) or "未分类",
            "core_levels": "; ".join(levels),
            "active": "1",
            "source_list": "seed_english_core_2026-11-25",
            "source_journal_key": journal.get("journal_key") or "",
            "official_url": journal.get("official_url") or journal.get("url") or "",
            "openalex_source_id": "",
            "crossref_journal_id": "",
            "rss_url": "",
            "rss_status": "",
            "source_priority": "",
            "last_audit_at": "",
            "notes": "",
        })
    known = {row["issn"] for row in rows if row["issn"]}
    for title, issn, publisher, url in FLAGSHIP:
        if issn in known:
            continue
        rows.append({
            "journal_id": journal_id(issn, title), "title": title, "title_zh": "",
            "title_norm": title_norm(title), "issn": issn, "eissn": "", "issns": issn,
            "publisher": publisher, "publisher_group": "nature" if "Nature" in publisher else "university_press",
            "subject": "综合性科学技术", "core_levels": "", "active": "1",
            "source_list": "seed_flagship_2026-11-25", "source_journal_key": "",
            "official_url": url, "openalex_source_id": "", "crossref_journal_id": "",
            "rss_url": "", "rss_status": "", "source_priority": "", "last_audit_at": "", "notes": "",
        })
    with WATCHLIST.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row["publisher_group"], []).append(row)
    sample: list[dict] = []
    for group, quota in QUOTAS.items():
        pool = buckets.get(group, [])
        if not pool:
            continue
        if len(pool) <= quota:
            sample.extend(pool)
            continue
        step = len(pool) / quota
        for index in range(quota):
            sample.append(pool[min(len(pool) - 1, int(index * step))])
    sample = list({row["journal_id"]: row for row in sample}.values())
    sample.sort(key=lambda row: (row["publisher_group"], row["title"]))
    with SAMPLE.open("w", encoding="utf-8-sig", newline="") as fh:
        fields = ["journal_id", "title", "issn", "eissn", "publisher", "publisher_group", "subject", "official_url"]
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sample)
    print("watchlist", WATCHLIST, len(rows))
    print("sample", SAMPLE, len(sample))
    for group, quota in QUOTAS.items():
        print(f"  {group:16s} pool={len(buckets.get(group, [])):3d} quota={quota:3d}")


if __name__ == "__main__":
    main()
