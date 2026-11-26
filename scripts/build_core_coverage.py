from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from difflib import get_close_matches
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"
CATALOG_PATH = ROOT / "journal_catalog" / "journals.json"
PENDING_PATH = ACADEMIC / "supplement_journals" / "pending_journals.json"

PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")

META = {
    "magetech_journals": ("摘要+DOI", "PDF链接"),
    "founder_journals": ("摘要+DOI", "无PDF"),
    "paperonce_journals": ("摘要+DOI", "无PDF"),
    "qinyun_journals": ("摘要+DOI", "无PDF"),
    "rhzh_journals": ("摘要+DOI", "无PDF"),
    "sancai_journals": ("摘要+DOI", "无PDF"),
    "cnki_cbpt": ("摘要(无DOI)", "无PDF"),
    "custom_toc_journals": ("标题+链接", "无PDF"),
    "vsb_journals": ("标题+链接", "无PDF"),
    "hep_mirror_journals": ("标题+链接", "无PDF"),
    "oa_rss_journals": ("摘要", "无PDF"),
    "supplement_journals": ("摘要+DOI", "无PDF"),
    "flagship_journals": ("摘要+DOI", "无PDF"),
}


def norm_title(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return PUNCT.sub("", text)


def base_title(value):
    text = re.sub(r"[（(][^）)]*[）)]", "", str(value or ""))
    return norm_title(text)


def norm_issn(value):
    return re.sub(r"[^0-9x]", "", str(value or "").lower()).upper()


def split_issns(value):
    result = []
    for token in re.split(r"[;,，\s]+", str(value or "")):
        digits = norm_issn(token)
        if len(digits) == 8:
            result.append(digits)
        elif len(digits) == 16:
            result.append(digits[:8])
    return result


def norm_cn(value):
    return re.sub(r"[^0-9a-z]", "", str(value or "").lower()).upper()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def package_modes():
    modes = {}
    for path in ACADEMIC.glob("*/manifest.json"):
        try:
            manifest = read_json(path)
        except Exception:
            continue
        collect_mode = (manifest.get("parameters_schema") or {}).get("properties", {}).get("collect_mode", {})
        enum = collect_mode.get("enum") or []
        package = path.parent.name
        if package in {"custom_toc_journals", "founder_journals", "paperonce_journals", "vsb_journals"}:
            modes[package] = "当期+关键词过滤"
        elif package == "oa_rss_journals":
            modes[package] = "当期RSS+关键词过滤"
        elif package == "hep_mirror_journals":
            modes[package] = "当期镜像+关键词过滤"
        elif package == "supplement_journals":
            modes[package] = "元数据检索"
        elif package == "flagship_journals":
            modes[package] = "关键词检索"
        elif "keywords" in enum and "latest_issue" in enum:
            modes[package] = "当期+关键词检索"
        elif "latest_issue" in enum:
            modes[package] = "仅当期"
        else:
            modes[package] = "其他"
    return modes


def platform_of(url):
    host = (urlsplit(str(url or "")).hostname or "").lower()
    rules = (
        ("cbpt.cnki.net", "CNKI CBPT/腾云"),
        ("magtechjournal.com", "玛格泰克"),
        ("magtech.org.cn", "玛格泰克"),
        ("magtech.com.cn", "玛格泰克"),
        ("hep.com.cn", "HEP"),
        ("founderss.cn", "北大方正"),
        ("paperonce.org", "PaperOnce"),
        ("ijournals.cn", "勤云"),
        ("cnjournals.org", "仁和汇智"),
        ("global-sci.com", "Global Science Press"),
        ("ccj.pku.edu.cn", "北大期刊网"),
        ("castjournals.cast.org.cn", "CAST镜像"),
    )
    for suffix, label in rules:
        if host.endswith(suffix):
            return label
    return host or "待探测"


def load_packages():
    rows = []
    for path in sorted(ACADEMIC.glob("*/journals.json")):
        try:
            data = read_json(path)
        except Exception:
            continue
        if isinstance(data, dict):
            data = data.get("journals", [])
        for row in data:
            row = dict(row)
            row["_package"] = path.parent.name
            rows.append(row)
    return rows


def load_catalog():
    rows = read_json(CATALOG_PATH)
    return rows if isinstance(rows, list) else rows.get("journals", [])


def load_pending():
    if not PENDING_PATH.exists():
        return {}
    rows = read_json(PENDING_PATH)
    return {row.get("journal_key"): row for row in rows}


def make_index(rows):
    by_issn, by_cn, by_name, by_base = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        cn = norm_cn(row.get("cn"))
        name_key = norm_title(name)
        base_key = base_title(name)
        for issn_value in [row.get("issn")] + (row.get("issns") or []):
            for issn in split_issns(issn_value):
                by_issn[issn].append(row)
        if cn:
            by_cn[cn].append(row)
        if name_key:
            by_name[name_key].append(row)
        if base_key and base_key != name_key:
            by_base[base_key].append(row)
    return {"issn": by_issn, "cn": by_cn, "name": by_name, "base": by_base}


def pick(row, keys):
    for key in keys:
        if key in row and str(row[key] or "").strip():
            return str(row[key]).strip()
    return ""


def default_level(filename):
    name = filename.lower()
    if "cssci" in name:
        return "CSSCI"
    if "cstpcd" in name:
        return "CSTPCD"
    if "cscd" in name:
        return "CSCD"
    if "pku" in name or "北大核心" in filename:
        return "北大核心"
    return Path(filename).stem


def read_core_lists(input_dir: Path):
    records = []
    for path in sorted(input_dir.glob("*.csv")):
        if path.name.startswith(("core-", "sample", "probe-", "review-", "b-")):
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                name = pick(row, ("journal_name", "name", "期刊名称", "期刊名", "刊名"))
                if not name:
                    continue
                records.append({
                    "name": name,
                    "issn": pick(row, ("issn", "ISSN")),
                    "cn": pick(row, ("cn", "CN", "国内刊号")),
                    "category": pick(row, ("category", "学科", "学科分类", "领域", "discipline")),
                    "list_type": pick(row, ("list_type", "类型", "核心类型", "list")) or default_level(path.name),
                    "edition": pick(row, ("edition", "版本", "年份")),
                    "source_url": pick(row, ("source_url", "url", "来源")),
                    "quality": pick(row, ("quality", "质量")),
                    "_file": path.name,
                })
    return records


def merge_records(records):
    merged = {}
    for row in records:
        key = norm_title(row["name"])
        if not key:
            continue
        item = merged.setdefault(key, {
            "name": row["name"],
            "issns": set(), "cns": set(), "levels": set(), "categories": set(),
            "editions": set(), "sources": set(), "qualities": set(), "files": set(),
        })
        for issn in split_issns(row.get("issn")):
            item["issns"].add(issn)
        if row.get("cn"):
            item["cns"].add(norm_cn(row["cn"]))
        if row.get("list_type"):
            item["levels"].add(row["list_type"])
        if row.get("category"):
            item["categories"].add(row["category"])
        if row.get("edition"):
            item["editions"].add(row["edition"])
        if row.get("source_url"):
            item["sources"].add(row["source_url"])
        if row.get("quality"):
            item["qualities"].add(row["quality"])
        item["files"].add(row.get("_file", ""))
    return list(merged.values())


def match_index(record, index, fuzzy_cutoff=0.97):
    for issn in record["issns"]:
        if issn in index["issn"]:
            return index["issn"][issn], "issn", 1.0
    for cn in record["cns"]:
        if cn in index["cn"]:
            return index["cn"][cn], "cn", 1.0
    name_key = norm_title(record["name"])
    if name_key in index["name"]:
        return index["name"][name_key], "name", 1.0
    base_key = base_title(record["name"])
    if base_key and base_key != name_key and base_key in index["base"]:
        return index["base"][base_key], "base_name", 0.95
    candidates = get_close_matches(name_key, list(index["name"]), n=1, cutoff=fuzzy_cutoff)
    if candidates:
        match = index["name"][candidates[0]][0]
        from difflib import SequenceMatcher
        return [match], "fuzzy", SequenceMatcher(None, name_key, candidates[0]).ratio()
    return [], "", 0.0


def unique(values):
    return ";".join(sorted({str(value) for value in values if str(value or "").strip()}))


def has_cjk(value):
    return bool(re.search(r"[一-鿿]", str(value or "")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(ROOT / ".local" / "core"))
    parser.add_argument("--output-dir", default=str(ROOT / "journal_catalog" / "core"))
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    input_dir, output_dir = Path(args.input_dir), Path(args.output_dir)
    core_files = [p for p in sorted(input_dir.glob("*.csv"))
                  if not p.name.startswith("core-") and not p.name.startswith("sample") and not p.name.startswith("probe-") and not p.name.startswith("review-") and not p.name.startswith("b-")]
    if not core_files:
        print(f"No core CSV files found in {input_dir}")
        print("Expected columns: journal_name,issn,cn,category,list_type,edition,source_url,quality")
        return 0

    core = merge_records(read_core_lists(input_dir))
    if not core:
        print("Core CSV files exist but no usable journal_name rows were found")
        return 1

    package_rows = load_packages()
    catalog_rows = load_catalog()
    pending = load_pending()
    package_index = make_index(package_rows)
    catalog_index = make_index(catalog_rows)
    modes = package_modes()
    catalog_by_key = {row.get("journal_key"): row for row in catalog_rows}

    coverage = []
    for record in core:
        pkg_match, pkg_method, pkg_score = match_index(record, package_index)
        cat_match, cat_method, cat_score = match_index(record, catalog_index)
        if pkg_match:
            status = "ambiguous" if pkg_method in ("base_name", "fuzzy") else "package_covered"
            matched_name = pkg_match[0].get("name", "")
            method, score = pkg_method, pkg_score
        elif cat_match:
            status = "catalog_only" if cat_method in ("issn", "cn", "name") else "ambiguous"
            matched_name = cat_match[0].get("name", "")
            method, score = cat_method, cat_score
        else:
            status, matched_name, method, score = "new_candidate", "", "", 0.0

        suggested_packages = sorted({row.get("_package") for row in pkg_match if row.get("_package")})
        packages = suggested_packages if status == "package_covered" else []
        catalog_row = cat_match[0] if cat_match else None
        catalog_status = ""
        if catalog_row:
            pending_row = pending.get(catalog_row.get("journal_key"))
            catalog_status = (pending_row or {}).get("status", "")
        url = ""
        if pkg_match:
            url = pkg_match[0].get("official_url") or pkg_match[0].get("url") or ""
        elif catalog_row:
            url = catalog_row.get("url") or ""
        if status == "ambiguous":
            meta_tags, pdf_status = "待复核", "待复核"
        else:
            meta_tags = unique(META[pkg][0] for pkg in packages if pkg in META) or "待探测"
            pdf_status = unique(META[pkg][1] for pkg in packages if pkg in META) or "待探测"
        language = "中文" if has_cjk(record["name"]) else "英文"
        levels = set(record["levels"])
        if status == "ambiguous":
            priority = "0-先复核"
        elif status in ("package_covered", "catalog_only"):
            priority = "已处理"
        elif language == "中文" and levels & {"北大核心", "来源期刊", "扩展版"}:
            priority = "1-中文社科核心"
        elif language == "中文" and levels & {"CSTPCD", "CSCD"}:
            priority = "2-中文理工医核心"
        elif language == "英文":
            priority = "3-英文刊"
        else:
            priority = "4-其他"

        coverage.append({
            "journal_name": record["name"],
            "core_levels": unique(record["levels"]),
            "categories": unique(record["categories"]),
            "editions": unique(record["editions"]),
            "status": status,
            "priority": priority,
            "language": language,
            "existing_packages": ";".join(packages),
            "suggested_packages": ";".join(suggested_packages) if status == "ambiguous" else "",
            "existing_modes": unique(modes.get(pkg, "") for pkg in packages),
            "platform": platform_of(url) if url else "待探测",
            "meta_tags": meta_tags,
            "pdf_status": pdf_status,
            "catalog_status": catalog_status,
            "official_url": url,
            "matched_name": matched_name,
            "match_method": method,
            "match_score": f"{score:.3f}" if score else "",
            "source_quality": unique(record["qualities"]) or "未标注",
            "sources": unique(record["sources"]),
            "issns": unique(record["issns"]),
            "cns": unique(record["cns"]),
        })

    order = {"package_covered": 0, "catalog_only": 1, "ambiguous": 2, "new_candidate": 3}
    coverage.sort(key=lambda row: (order.get(row["status"], 9), row["journal_name"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"core-coverage-{args.date}.csv"
    fieldnames = list(coverage[0].keys())
    with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(coverage)

    candidates = [row for row in coverage if row["status"] in ("new_candidate", "ambiguous")]
    candidate_path = output_dir / f"core-new-candidates-{args.date}.csv"
    candidate_fields = ["journal_name", "core_levels", "categories", "editions", "status", "priority", "language",
                        "platform", "existing_packages", "suggested_packages", "matched_name", "match_method",
                        "match_score", "source_quality", "issns", "cns", "sources"]
    with candidate_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate_fields)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in candidate_fields} for row in candidates])

    status_counts = Counter(row["status"] for row in coverage)
    level_counts = Counter()
    for row in coverage:
        for level in (row["core_levels"] or "未分级").split(";"):
            level_counts[(level, row["status"])] += 1
    category_counts = Counter()
    for row in coverage:
        for category in (row["categories"] or "未分类").split(";"):
            category_counts[(category, row["status"])] += 1
    package_counts = Counter()
    for row in coverage:
        for package in (row["existing_packages"] or "").split(";"):
            if package:
                package_counts[package] += 1

    priority_counts = Counter((row["priority"], row["status"]) for row in coverage)
    language_counts = Counter((row["language"], row["status"]) for row in coverage)
    summary = {
        "date": args.date,
        "input_files": [p.name for p in core_files],
        "total_core_journals": len(coverage),
        "status": dict(status_counts),
        "by_level": {level: {status: count for (lvl, status), count in level_counts.items() if lvl == level}
                     for level in sorted({lvl for lvl, _ in level_counts})},
        "by_package": dict(package_counts.most_common()),
        "by_priority": {priority: {status: count for (pri, status), count in priority_counts.items() if pri == priority}
                         for priority in sorted({pri for pri, _ in priority_counts})},
        "by_language": {language: {status: count for (lang, status), count in language_counts.items() if lang == language}
                         for language in sorted({lang for lang, _ in language_counts})},
        "report_csv": str(report_path),
        "candidates_csv": str(candidate_path),
    }
    summary_path = output_dir / f"core-coverage-{args.date}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# 国内核心期刊覆盖报告（{args.date}）",
        "",
        f"- 输入文件：{', '.join(p.name for p in core_files)}",
        f"- 核心期刊总数：{len(coverage)}",
        f"- 状态：已入包 {status_counts.get('package_covered', 0)}，仅在目录 {status_counts.get('catalog_only', 0)}，"
        f"歧义 {status_counts.get('ambiguous', 0)}，新增候选 {status_counts.get('new_candidate', 0)}",
        "",
        "## 按核心级别",
        "",
        "| 核心级别 | 总数 | 已入包 | 仅在目录 | 歧义 | 新增候选 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for level in sorted({lvl for lvl, _ in level_counts}):
        def count(status):
            return level_counts.get((level, status), 0)
        total = sum(count(status) for status in ("package_covered", "catalog_only", "ambiguous", "new_candidate"))
        lines.append(f"| {level} | {total} | {count('package_covered')} | {count('catalog_only')} | "
                     f"{count('ambiguous')} | {count('new_candidate')} |")
    lines += ["", "## 按优先级", "", "| 优先级 | 总数 | 已入包 | 仅在目录 | 歧义 | 新增候选 |", "|---|---:|---:|---:|---:|---:|"]
    for priority in sorted({pri for pri, _ in priority_counts}):
        def pcount(status):
            return priority_counts.get((priority, status), 0)
        total = sum(pcount(status) for status in ("package_covered", "catalog_only", "ambiguous", "new_candidate"))
        lines.append(f"| {priority} | {total} | {pcount('package_covered')} | {pcount('catalog_only')} | "
                     f"{pcount('ambiguous')} | {pcount('new_candidate')} |")
    lines += ["", "## 按学科（前 20）", "", "| 学科 | 总数 | 已入包 | 新增候选 |", "|---|---:|---:|---:|"]
    for category, _ in Counter({category: sum(count for (cat, _), count in category_counts.items() if cat == category)
                                for category in {cat for cat, _ in category_counts}}).most_common(20):
        total = sum(count for (cat, _), count in category_counts.items() if cat == category)
        lines.append(f"| {category} | {total} | {category_counts.get((category, 'package_covered'), 0)} | "
                     f"{category_counts.get((category, 'new_candidate'), 0)} |")
    lines += ["", "## 已入包（按包）", "", "| 包 | 核心刊数 |", "|---|---:|"]
    for package, count in package_counts.most_common():
        lines.append(f"| {package} | {count} |")
    lines += [
        "",
        "## 输出",
        "",
        f"- 逐刊覆盖：[{report_path.name}]({report_path.name})",
        f"- 新增候选：[{candidate_path.name}]({candidate_path.name})",
        "",
        "> 说明：核心名单可能受版权限制，本报告仅在本地研究使用；`reference` 表示非官方来源，需要复核。",
    ]
    markdown_path = output_dir / f"core-coverage-{args.date}.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:8]))
    print(f"report: {report_path}")
    print(f"candidates: {candidate_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())