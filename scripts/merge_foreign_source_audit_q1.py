from __future__ import annotations

import csv
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOREIGN = ROOT / "journal_catalog" / "foreign"
SAMPLE = FOREIGN / "foreign_q1_audit_sample_2026-11-25.csv"
OUT_CSV = FOREIGN / "foreign_source_audit_q1_2026-11-25.csv"
OUT_MD = FOREIGN / "foreign_source_audit_q1_2026-11-25.md"
AS_OF = date(2026, 11, 25)


def read(name: str) -> list[dict]:
    path = FOREIGN / name
    return list(csv.DictReader(path.open(encoding="utf-8-sig", newline=""))) if path.exists() else []


def num(value) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def rate(part, total) -> float:
    return round(num(part) / num(total) * 100, 1) if num(total) else 0.0


def lag(value: str) -> str:
    text = str(value or "").strip()[:10]
    try:
        return str((AS_OF - date.fromisoformat(text)).days)
    except ValueError:
        return ""


def main() -> None:
    sample = read("foreign_q1_audit_sample_2026-11-25.csv")
    rss_map = {row["journal_id"]: row for row in read("foreign_rss_mapping_q1_2026-11-25.csv")}
    rss = {row["journal_id"]: row for row in read("foreign_rss_audit_q1_2026-11-25.csv")}
    openalex = {row["journal_id"]: row for row in read("foreign_openalex_audit_q1_2026-11-25.csv")}
    crossref = {row["journal_id"]: row for row in read("foreign_crossref_audit_q1_2026-11-25.csv")}
    pubmed = {row["journal_id"]: row for row in read("foreign_pubmed_audit_q1_2026-11-25.csv")}
    rows: list[dict] = []
    decisions = Counter()
    for base in sample:
        key = base["journal_id"]
        mapping = rss_map.get(key, {})
        ra = rss.get(key, {})
        oa = openalex.get(key, {})
        cr = crossref.get(key, {})
        pm = pubmed.get(key, {})
        oa_items = num(oa.get("items_90d"))
        cr_items = num(cr.get("items_90d"))
        pm_items = num(pm.get("items_90d"))
        rss_items = num(ra.get("items_90d"))
        oa_abs = rate(oa.get("abstract_items"), oa_items)
        cr_abs = rate(cr.get("abstract_items"), cr_items)
        pm_abs = rate(pm.get("abstract_items"), pm_items)
        if oa_items:
            primary = "openalex"
            fallback = "crossref" if cr_items else ""
        elif cr_items:
            primary = "crossref"
            fallback = ""
        elif pm_items:
            primary = "pubmed"
            fallback = ""
        elif rss_items:
            primary = "rss_signal"
            fallback = ""
        else:
            primary = "none"
            fallback = ""
        abstract_candidates = [("pubmed", pm_items, pm_abs), ("openalex", oa_items, oa_abs), ("crossref", cr_items, cr_abs)]
        abstract_candidates = [value for value in abstract_candidates if value[1] > 0]
        abstract_source = max(abstract_candidates, key=lambda value: value[2])[0] if abstract_candidates else ""
        doi_source = "openalex" if num(oa.get("doi_items")) else "crossref" if num(cr.get("doi_items")) else "pubmed" if num(pm.get("doi_items")) else ""
        if primary == "none" and rss_items:
            decision = "rss_signal_only"
        elif primary == "none":
            decision = "no_recent_items"
        elif primary == "openalex":
            decision = "openalex_primary" + ("_crossref_fallback" if fallback else "")
        elif primary == "crossref":
            decision = "crossref_primary"
        elif primary == "pubmed":
            decision = "pubmed_primary"
        else:
            decision = primary
        decisions[decision] += 1
        latest = max([value for value in (oa.get("latest_date"), cr.get("latest_date"), pm.get("latest_date"), ra.get("latest_date")) if value] or [""])
        notes = []
        if oa.get("truncated") == "True":
            notes.append("OpenAlex >100，需分页")
        if cr.get("truncated") == "True":
            notes.append("Crossref >100，需分页")
        if pm.get("truncated") == "True":
            notes.append("PubMed >100，需分页")
        if mapping.get("match_type") == "fuzzy":
            notes.append("RSS 模糊匹配，需人工确认")
        if ra.get("status") not in ("", "ok"):
            notes.append(f"RSS {ra.get('status')}")
        rows.append({
            "journal_id": key,
            "title": base["title"],
            "issn": base["issn"],
            "eissn": base["eissn"],
            "publisher": base["publisher"],
            "edition": base["edition"],
            "jif": base["jif"],
            "jif_percentile": base["jif_percentile"],
            "primary_category": base["primary_category"],
            "scopus_active": base["scopus_active"],
            "scopus_top_levels": base["scopus_top_levels"],
            "rss_match": mapping.get("match_type", "miss"),
            "rss_url": mapping.get("rss_url", ""),
            "rss_items_90d": rss_items,
            "rss_latest": ra.get("latest_date", ""),
            "rss_abstract_items": num(ra.get("abstract_items")),
            "rss_doi_items": num(ra.get("doi_items")),
            "rss_status": ra.get("status", "not_audited"),
            "openalex_status": oa.get("status", ""),
            "openalex_items_90d": oa_items,
            "openalex_total": oa.get("total_count", ""),
            "openalex_latest": oa.get("latest_date", ""),
            "openalex_abstract_rate": oa_abs,
            "openalex_doi_rate": rate(oa.get("doi_items"), oa_items),
            "openalex_truncated": oa.get("truncated", ""),
            "crossref_status": cr.get("status", ""),
            "crossref_items_90d": cr_items,
            "crossref_total": cr.get("total_count", ""),
            "crossref_latest": cr.get("latest_date", ""),
            "crossref_abstract_rate": cr_abs,
            "crossref_doi_rate": rate(cr.get("doi_items"), cr_items),
            "crossref_truncated": cr.get("truncated", ""),
            "pubmed_status": pm.get("status", ""),
            "pubmed_items_90d": pm_items,
            "pubmed_latest": pm.get("latest_date", ""),
            "pubmed_abstract_rate": pm_abs,
            "pubmed_doi_rate": rate(pm.get("doi_items"), pm_items),
            "primary_source": primary,
            "fallback_source": fallback,
            "abstract_source": abstract_source,
            "doi_source": doi_source,
            "rss_role": "signal" if rss_items else "none",
            "latest_any": latest,
            "lag_days": lag(latest),
            "decision": decision,
            "notes": "; ".join(notes),
        })
    rows.sort(key=lambda row: (row["decision"], row["edition"], row["title"]))
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    oa_hit = sum(1 for row in rows if row["openalex_items_90d"] > 0)
    cr_hit = sum(1 for row in rows if row["crossref_items_90d"] > 0)
    pm_hit = sum(1 for row in rows if row["pubmed_items_90d"] > 0)
    rss_hit = sum(1 for row in rows if row["rss_items_90d"] > 0)
    rss_mapped = sum(1 for row in rows if row["rss_match"] in ("exact", "fuzzy"))
    lines = [
        "# Q1 全学科源覆盖审计汇总（200 本样本）",
        "",
        f"- 样本：{len(rows)} 本（JCR 2025 Q1，来自 {len(set(row['journal_id'] for row in rows))} 个唯一 ID）",
        f"- OpenAlex 有记录：{oa_hit}/{len(rows)}（{oa_hit/len(rows)*100:.1f}%）",
        f"- Crossref 有记录：{cr_hit}/{len(rows)}（{cr_hit/len(rows)*100:.1f}%）",
        f"- PubMed 有记录：{pm_hit}/{sum(1 for row in rows if row['pubmed_status'])}（仅生物医学子集）",
        f"- RSS 映射命中：{rss_mapped}/{len(rows)}；RSS 90 天有更新：{rss_hit}/{len(rows)}",
        "",
        "## 选源决策",
        "",
    ]
    for decision, count in decisions.most_common():
        lines.append(f"- {decision}: {count}")
    lines += [
        "",
        "## 结论",
        "",
        "- OpenAlex 是主源：覆盖高、DOI 接近 100%，但摘要按出版商差异大（Elsevier/Springer/Nature 部分低）。",
        "- Crossref 是 DOI/元数据兜底：DOI 100%，摘要覆盖低，不能单独承担摘要。",
        "- PubMed 只适合生物医学子集：DOI 100%、摘要约 75%，但要处理年份级 PubDate 和 ISSN 分裂。",
        "- RSS 只能当“新一期信号”：Q1 全量命中约 31%，ScienceDirect 的 feed 无摘要/DOI/精确日期，不能当元数据主源。",
        "- 全量 5,279 本 Q1 尚未逐本审计；本表是 200 本分层样本，用于确定按源适配策略。",
        "",
        f"CSV：[{OUT_CSV.name}]({OUT_CSV.name})",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("csv", OUT_CSV, len(rows))
    print("md", OUT_MD)
    print("openalex_hit", oa_hit, "crossref_hit", cr_hit, "pubmed_hit", pm_hit, "rss_hit", rss_hit)
    print("decisions", dict(decisions))


if __name__ == "__main__":
    main()
