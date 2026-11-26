from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "journal_catalog" / "source" / "periodicals_2026-11-25"
JCR_DIR = SOURCE / "JCR爬虫" / "JCR_最终版"
SCOPUS_CSV = ROOT / "journal_catalog" / "foreign" / "scopus_sources_2026-11-25.csv"
OUT_DIR = ROOT / "journal_catalog" / "foreign"
WATCHLIST = OUT_DIR / "foreign_journals_q1_2026-11-25.csv"
SAMPLE = OUT_DIR / "foreign_q1_audit_sample_2026-11-25.csv"
SUMMARY = OUT_DIR / "foreign_q1_summary_2026-11-25.md"
TOP_LEVELS = ["Life Sciences", "Health Sciences", "Physical Sciences", "Social Sciences"]


def norm_issn(value: str) -> str:
    text = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return f"{text[:4]}-{text[4:]}" if len(text) == 8 else ""


def title_norm(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    if text.startswith("the "):
        text = text[4:]
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def edition(value: str) -> str:
    text = str(value or "")
    if "Science Citation Index Expanded" in text:
        return "SCIE"
    if "Social Sciences Citation Index" in text:
        return "SSCI"
    if "Arts & Humanities" in text:
        return "AHCI"
    if "Emerging Sources" in text:
        return "ESCI"
    return text or "?"


def load_scopus() -> tuple[dict[str, dict], dict[str, dict], Counter]:
    by_issn: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    stats = Counter()
    with SCOPUS_CSV.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        subject_names = header[25:52]
        for row in reader:
            if len(row) < 52:
                continue
            record = {
                "scopus_source_id": row[0].strip(),
                "scopus_title": row[1].strip(),
                "scopus_issn": norm_issn(row[2]),
                "scopus_eissn": norm_issn(row[3]),
                "scopus_active": row[4].strip() or "Unknown",
                "scopus_coverage": row[5].strip(),
                "scopus_source_type": row[12].strip(),
                "scopus_publisher": row[18].strip(),
                "scopus_asjc": row[20].strip(),
                "scopus_top_levels": "; ".join(value.strip() for value in row[21:25] if value.strip()),
                "scopus_subjects": "; ".join(name.strip() for name, value in zip(subject_names, row[25:52]) if value.strip()),
            }
            for key in (record["scopus_issn"], record["scopus_eissn"]):
                if key:
                    existing = by_issn.get(key)
                    if existing is None or (existing["scopus_active"] != "Active" and record["scopus_active"] == "Active"):
                        by_issn[key] = record
            key = title_norm(record["scopus_title"])
            if key:
                by_title.setdefault(key, record)
            stats[record["scopus_active"]] += 1
    return by_issn, by_title, stats


def main() -> None:
    by_issn, by_title, scopus_stats = load_scopus()
    rows: list[dict] = []
    q_stats = Counter()
    editions = Counter()
    for path in JCR_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if str(data.get("quartile") or "") != "Q1":
            continue
        issns = [norm_issn(data.get("issn")), norm_issn(data.get("eissn"))]
        issns = list(dict.fromkeys(value for value in issns if value))
        issn, eissn = (issns + ["", ""])[:2]
        title = str(data.get("journalName") or "").strip()
        categories = [str(value) for value in data.get("category") or []]
        category_quartiles = data.get("categoryQuartiles") or []
        stats = {}
        scopus = by_issn.get(issn) or by_issn.get(eissn)
        match_type = "issn" if scopus else ""
        if scopus is None:
            scopus = by_title.get(title_norm(title))
            match_type = "title" if scopus else ""
        scopus = scopus or {}
        row = {
            "journal_id": hashlib.sha1(f"{issn or eissn}|{title}".encode("utf-8")).hexdigest()[:16],
            "title": title,
            "title_norm": title_norm(title),
            "issn": issn,
            "eissn": eissn,
            "publisher": str(data.get("publisher") or data.get("PUBLISHER") or ""),
            "jcr_year": str(data.get("jcrYear") or ""),
            "edition": edition(data.get("EDITION")),
            "jcr_quartile": str(data.get("quartile") or ""),
            "jif_quartile": str(data.get("quartile") or ""),
            "jif": str(data.get("jif2019") or ""),
            "jif_5y": str(data.get("jif5Years") or ""),
            "jif_percentile": str(data.get("jifPercentile") or ""),
            "jci": str(data.get("jci") or ""),
            "jci_quartile": str(data.get("jciQuartile") or ""),
            "ais_quartile": str(data.get("aisQuartile") or ""),
            "five_year_quartile": str(data.get("fiveYearJifQuartile") or ""),
            "jif_rank": str(data.get("jifRank") or ""),
            "jci_rank": str(data.get("jciRank") or ""),
            "ais_rank": str(data.get("aisRank") or ""),
            "total_cites": str(data.get("totalCites") or ""),
            "total_articles": str(data.get("totalArticles") or ""),
            "citable_items": str(data.get("citableItems") or ""),
            "oa_gold_pct": str(data.get("percentageOAGold") or ""),
            "categories": "; ".join(categories),
            "primary_category": categories[0] if categories else "",
            "category_quartiles_json": json.dumps(category_quartiles, ensure_ascii=False, separators=(",", ":")),
            "scopus_source_id": scopus.get("scopus_source_id", ""),
            "scopus_title": scopus.get("scopus_title", ""),
            "scopus_active": scopus.get("scopus_active", "Unknown"),
            "scopus_coverage": scopus.get("scopus_coverage", ""),
            "scopus_source_type": scopus.get("scopus_source_type", ""),
            "scopus_publisher": scopus.get("scopus_publisher", ""),
            "scopus_asjc": scopus.get("scopus_asjc", ""),
            "scopus_top_levels": scopus.get("scopus_top_levels", ""),
            "scopus_subjects": scopus.get("scopus_subjects", ""),
            "scopus_match": match_type,
            "watchlist_status": "active" if scopus.get("scopus_active") == "Active" else "inactive" if scopus.get("scopus_active") == "Inactive" else "unknown",
            "include_daily": "no" if scopus.get("scopus_active") == "Inactive" else "yes",
            "source_list": "JCR_2025_Q1_all_disciplines",
            "rss_url": "",
            "rss_status": "",
            "openalex_source_id": "",
            "crossref_journal_id": "",
            "source_priority": "",
            "notes": "",
        }
        rows.append(row)
        q_stats[row["watchlist_status"]] += 1
        editions[row["edition"]] += 1
    rows.sort(key=lambda row: (row["edition"], row["primary_category"], row["title"]))
    with WATCHLIST.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["include_daily"] == "no":
            continue
        top = next((name for name in TOP_LEVELS if name in row["scopus_top_levels"]), "Unknown")
        groups[top].append(row)
    sample: list[dict] = []
    for name in TOP_LEVELS + ["Unknown"]:
        pool = groups.get(name, [])
        quota = 40
        if len(pool) <= quota:
            sample.extend(pool)
        else:
            step = len(pool) / quota
            sample.extend(pool[min(len(pool) - 1, int(index * step))] for index in range(quota))
    sample = list({row["journal_id"]: row for row in sample}.values())
    if len(sample) < 200:
        used = {row["journal_id"] for row in sample}
        rest = [row for row in rows if row["include_daily"] != "no" and row["journal_id"] not in used]
        step = len(rest) / max(1, 200 - len(sample))
        sample.extend(rest[min(len(rest) - 1, int(index * step))] for index in range(200 - len(sample)))
    sample = list({row["journal_id"]: row for row in sample}.values())
    sample.sort(key=lambda row: (next((name for name in TOP_LEVELS if name in row["scopus_top_levels"]), "Unknown"), row["title"]))
    fields = ["journal_id", "title", "issn", "eissn", "publisher", "edition", "jif", "jif_percentile",
              "jif_rank", "primary_category", "categories", "scopus_active", "scopus_top_levels",
              "scopus_subjects", "scopus_match", "official_url"]
    # official_url is not in JCR; keep empty column for downstream agents to fill if needed
    for row in sample:
        row.setdefault("official_url", "")
    with SAMPLE.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sample)

    lines = [
        "# JCR 2025 Q1 全学科 watchlist",
        "",
        f"- Q1 总刊数：{len(rows)}",
        f"- 按 Scopus 状态：{dict(q_stats)}",
        f"- 按 Edition：{dict(editions)}",
        f"- 审计样本：{len(sample)} 本（排除已知 Inactive，按 Scopus 四大 Top level 分层）",
        "",
        "## 样本 Top level 分布",
    ]
    for name in TOP_LEVELS + ["Unknown"]:
        lines.append(f"- {name}: {sum(1 for row in sample if next((x for x in TOP_LEVELS if x in row['scopus_top_levels']), 'Unknown') == name)}")
    lines += ["", "## 主要 JCR 学科（Q1 全量前 30）", ""]
    for name, count in Counter(row["primary_category"] for row in rows).most_common(30):
        lines.append(f"- {name}: {count}")
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("watchlist", WATCHLIST, len(rows))
    print("sample", SAMPLE, len(sample))
    print("scopus rows by active", dict(scopus_stats))
    print("q1 by scopus status", dict(q_stats))
    print("q1 by edition", dict(editions))
    print("sample top levels", Counter(next((name for name in TOP_LEVELS if name in row["scopus_top_levels"]), "Unknown") for row in sample))
    print("summary", SUMMARY)


if __name__ == "__main__":
    main()
