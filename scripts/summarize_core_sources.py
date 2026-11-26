from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "journal_catalog" / "core"
DATE = "2026-11-25"
COVERAGE_DATE = "2026-11-25"

LIST_LABELS = {
    "来源期刊": "CSSCI 来源期刊",
    "扩展版": "CSSCI 扩展版",
    "北大核心": "北大核心",
    "CSTPCD": "CSTPCD 科技核心",
    "CSCD": "CSCD",
}

PACKAGE_LABELS = {
    "cnki_cbpt": "CNKI CBPT/腾云",
    "magetech_journals": "玛格泰克",
    "qinyun_journals": "勤云",
    "rhzh_journals": "仁和汇智",
    "founder_journals": "北大方正",
    "paperonce_journals": "PaperOnce",
    "vsb_journals": "VSB",
    "hep_mirror_journals": "HEP 镜像",
    "custom_toc_journals": "自定义/独立 CMS",
    "supplement_journals": "OpenAlex/Crossref",
    "sancai_journals": "西安三才",
    "oa_rss_journals": "OA RSS",
    "sciengine_journals": "SciEngine",
}


def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def labels(core_levels):
    result = []
    for value in str(core_levels or "").split(";"):
        value = value.strip()
        if value:
            result.append(LIST_LABELS.get(value, value))
    return result or ["未分级"]


def platform_group(row):
    packages = [pkg for pkg in str(row.get("existing_packages") or "").split(";") if pkg]
    if packages:
        return ";".join(sorted({PACKAGE_LABELS.get(pkg, pkg) for pkg in packages}))
    if row.get("status") == "ambiguous":
        return "版本歧义（待复核）"
    if row.get("status") == "catalog_only":
        return "2377 内已阻断/待适配"
    return "待探测"


def main():
    rows = read_csv(CORE / f"core-coverage-{COVERAGE_DATE}.csv")
    applied = read_csv(CORE / "core-additions-applied-2026-11-22.csv") + read_csv(CORE / "core-stem-additions-applied-2026-11-22.csv") + read_csv(CORE / f"core-social-additions-applied-2026-11-23.csv") + read_csv(CORE / f"core-stem2-additions-applied-2026-11-23.csv") + read_csv(CORE / f"core-social2-additions-applied-2026-11-23.csv") + read_csv(CORE / f"core-social3-additions-applied-2026-11-23.csv") + read_csv(CORE / f"core-social4-additions-applied-2026-11-23.csv") + read_csv(CORE / f"core-en-additions-applied-2026-11-23.csv") + read_csv(CORE / f"core-supplement-additions-applied-2026-11-24.csv") + read_csv(CORE / f"core-cmacmc-additions-applied-2026-11-24.csv") + read_csv(CORE / f"core-h-additions-applied-2026-11-24.csv") + read_csv(CORE / f"core-g7-additions-applied-2026-11-24.csv") + read_csv(CORE / f"core-a3-additions-applied-2026-11-24.csv") + read_csv(CORE / f"core-a4-additions-applied-2026-11-24.csv") + read_csv(CORE / f"core-a5g6-additions-applied-2026-11-24.csv") + read_csv(CORE / "workbuddy" / "b-applied-2026-11-24.csv") + read_csv(CORE / "c-group" / "c-main-applied-2026-11-24.csv") + read_csv(CORE / "english-17-supplement-applied-2026-11-24.csv") + read_csv(CORE / "sciengine-applied-2026-11-25.csv") + read_csv(CORE / "workbuddy" / "accepted-known-applied-2026-11-25.csv") + read_csv(CORE / "workbuddy" / "custom-applied-2026-11-25.csv")
    review = read_csv(CORE / "core-additions-review-2026-11-22.csv")
    review_json_path = ROOT / ".local" / "core" / "probe-results-review.json"
    review_results = json.loads(review_json_path.read_text(encoding="utf-8")) if review_json_path.exists() else []
    review_remaining = [row for row in review_results if row.get("status") != "ok"]
    review_ok = len(review_results) - len(review_remaining)

    by_list = defaultdict(Counter)
    by_platform = defaultdict(Counter)
    by_category = defaultdict(Counter)
    by_priority = Counter()
    by_quality = Counter()
    by_language = Counter()
    by_status = Counter(row.get("status") for row in rows)
    for row in rows:
        status = row.get("status", "")
        by_priority[(row.get("priority", ""), status)] += 1
        by_quality[row.get("source_quality", "")] += 1
        by_language[(row.get("language", ""), status)] += 1
        for label in labels(row.get("core_levels")):
            by_list[label][status] += 1
        by_platform[platform_group(row)][status] += 1
        for category in str(row.get("categories") or "未分类").split(";"):
            by_category[category or "未分类"][status] += 1

    applied_by_package = Counter(row.get("target_package", "") for row in applied)
    applied_by_level = Counter()
    for row in applied:
        for label in labels(row.get("core_levels")):
            applied_by_level[label] += 1
    review_by_platform = Counter(row.get("platform", "") for row in review_remaining)

    summary = {
        "date": DATE,
        "total_core": len(rows),
        "status": dict(by_status),
        "by_list": {key: dict(value) for key, value in sorted(by_list.items())},
        "by_platform": {key: dict(value) for key, value in sorted(by_platform.items(), key=lambda item: -sum(item[1].values()))},
        "by_category": {key: dict(value) for key, value in sorted(by_category.items(), key=lambda item: -sum(item[1].values()))},
        "by_priority": {f"{key[0]}|{key[1]}": value for key, value in sorted(by_priority.items())},
        "by_language": {f"{key[0]}|{key[1]}": value for key, value in sorted(by_language.items())},
        "by_quality": dict(by_quality),
        "applied": len(applied),
        "applied_by_package": dict(applied_by_package.most_common()),
        "applied_by_level": dict(applied_by_level.most_common()),
        "review_total": len(review),
        "review_ok": review_ok,
        "review_remaining": len(review_remaining),
        "review_by_platform": dict(review_by_platform.most_common()),
    }
    (CORE / f"core-source-summary-{DATE}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    statuses = ["package_covered", "catalog_only", "ambiguous", "new_candidate"]
    lines = [
        f"# 国内核心刊来源统计（{DATE}）",
        "",
        f"- 核心刊总数：{len(rows)}",
        f"- 已入包：{by_status.get('package_covered', 0)}",
        f"- 仅在 2377 目录：{by_status.get('catalog_only', 0)}",
        f"- 版本歧义：{by_status.get('ambiguous', 0)}",
        f"- 适配复核剩余：{len(review_remaining)}",
        f"- 新增候选：{by_status.get('new_candidate', 0)}",
        f"- 核心刊补录入包：{len(applied)}；复核完成：{review_ok}，待复核：{len(review_remaining)}",
        "",
        "> 核心名单可重叠，按名单统计的合计会大于去重后的期刊数。",
        "",
        "## 一、按核心名单来源",
        "",
        "| 名单 | 总数 | 已入包 | 仅在目录 | 待复核 | 新增候选 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label in LIST_LABELS.values():
        counter = by_list.get(label, Counter())
        total = sum(counter.values())
        lines.append(f"| {label} | {total} | {counter.get('package_covered', 0)} | "
                     f"{counter.get('catalog_only', 0)} | {counter.get('ambiguous', 0)} | "
                     f"{counter.get('new_candidate', 0)} |")
    lines += ["", "## 二、按平台/供应商来源", "", "| 平台/供应商 | 总数 | 已入包 | 仅在目录 | 待复核 | 新增候选 |",
              "|---|---:|---:|---:|---:|---:|"]
    for label, counter in sorted(by_platform.items(), key=lambda item: -sum(item[1].values())):
        total = sum(counter.values())
        lines.append(f"| {label} | {total} | {counter.get('package_covered', 0)} | "
                     f"{counter.get('catalog_only', 0)} | {counter.get('ambiguous', 0)} | "
                     f"{counter.get('new_candidate', 0)} |")
    lines += ["", "## 三、按学科（前 20）", "", "| 学科 | 总数 | 已入包 | 新增候选 |", "|---|---:|---:|---:|"]
    for category, counter in sorted(by_category.items(), key=lambda item: -sum(item[1].values()))[:20]:
        total = sum(counter.values())
        lines.append(f"| {category} | {total} | {counter.get('package_covered', 0)} | "
                     f"{counter.get('new_candidate', 0)} |")
    lines += ["", "## 四、按优先级", "", "| 优先级 | 总数 | 已入包 | 待复核 | 新增候选 |", "|---|---:|---:|---:|---:|"]
    for priority in ("1-中文社科核心", "2-中文理工医核心", "3-英文刊", "0-先复核", "已处理"):
        counter = Counter()
        for (pri, status), count in by_priority.items():
            if pri == priority:
                counter[status] += count
        if not counter:
            continue
        total = sum(counter.values())
        lines.append(f"| {priority} | {total} | {counter.get('package_covered', 0)} | "
                     f"{counter.get('ambiguous', 0)} | {counter.get('new_candidate', 0)} |")
    lines += ["", "## 五、核心刊补录入包", "", "| 包 | 数量 |", "|---|---:|"]
    for package, count in applied_by_package.most_common():
        lines.append(f"| {package} | {count} |")
    lines += ["", "按核心名单：", ""]
    for label, count in applied_by_level.most_common():
        lines.append(f"- {label}：{count}")
    lines += ["", f"## 六、待复核（剩余 {len(review_remaining)} 本）", "", "| 平台 | 数量 |", "|---|---:|"]
    for platform, count in review_by_platform.most_common():
        lines.append(f"| {platform} | {count} |")
    lines += [
        "",
        "## 七、名单质量",
        "",
        f"- 来源质量分布：{json.dumps(dict(by_quality), ensure_ascii=False)}",
        "- CSSCI/CSTPCD/CSCD/北大核心均为公开转载或参考版；正式采信前需用官方/授权版本复核。",
        "- 名单级来源 URL 见 `.local/core/*-meta.json`；逐刊名单来源见 coverage CSV 的 `sources` 列。",
        "",
        "## 八、后续安排建议",
        "",
        "1. 先做中文理工医 559 本（CSTPCD/CSCD）——本轮已开 6 个 agent 探测前 300 本，剩余 259 本下一批。",
        "2. 处理 28 本待复核：4 本 custom 找单期入口，其余 24 本补适配/换入口。",
        "3. 再做中文社科剩余 1428 本；英文 324 本暂缓。",
        "4. 每完成一批，重跑 `build_core_coverage.py` 与 `summarize_core_sources.py`，更新来源统计。",
    ]
    markdown_path = CORE / f"core-source-summary-{DATE}.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:20]))
    print("json:", CORE / f"core-source-summary-{DATE}.json")
    print("markdown:", markdown_path)


if __name__ == "__main__":
    main()