from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "journal_catalog" / "core"

SOCIAL = [
    "经济", "金融", "货币", "贸易", "会计", "审计", "统计", "管理", "政治", "法学",
    "法律", "社会", "人口", "民族", "教育", "心理", "体育", "语言", "外语", "语文",
    "文学", "历史", "考古", "哲学", "宗教", "艺术", "音乐", "戏剧", "电影", "电视",
    "新闻", "出版", "档案", "图书", "信息资源", "文化", "马克思主义", "人才", "公安",
    "博物馆", "中国学", "汉学", "人文经济地理", "绘画", "雕塑", "工艺美术", "舞蹈",
    "财政",
]
MED = [
    "医药", "医学", "临床", "内科", "外科", "儿科", "肿瘤", "护理", "药学", "卫生",
    "中医", "预防", "特种医学", "基础医学",
]
AGRI = ["农业", "林业", "畜牧", "植物保护", "园艺", "烟草", "农学"]
ENG = [
    "工程", "工业", "技术", "机械", "电子", "电工", "自动控制", "信息科学", "系统科学",
    "通信", "材料", "建筑", "土木", "水利", "交通", "铁路", "水路", "航空", "航天",
    "矿业", "煤矿", "冶金", "能源", "石油", "天然气", "核", "原子能", "动力", "轻工",
    "纺织", "食品", "印刷", "造纸", "皮革", "木材", "制冷", "武器", "安全", "环境",
    "资源", "测绘", "通用技术", "化工",
]
SCI = [
    "数学", "物理", "化学", "生物", "地球", "地质", "地理", "海洋", "气象", "天文",
    "力学", "自然", "植物学", "动物学",
]


def group(category):
    text = str(category or "").strip()
    if not text:
        return "未分类"
    if text == "英文版期刊":
        return "英文刊（学科未细分）"
    if "畜牧" in text or "动物医学" in text:
        return "农业科学"
    if any(key in text for key in MED):
        return "医药卫生"
    if any(key in text for key in SOCIAL):
        return "人文社科"
    if any(key in text for key in AGRI):
        return "农业科学"
    if text in ("综合性科学技术", "综合理工农医类"):
        return "综合/交叉"
    if text == "高校学报":
        return "综合/高校学报"
    if text == "科学研究":
        return "综合/其他"
    if any(key in text for key in ENG):
        return "工学"
    if any(key in text for key in SCI):
        return "理学"
    return "未分类"


def primary_category(categories):
    cats = [item.strip() for item in str(categories or "").split(";") if item.strip()]
    if not cats:
        return ""
    if cats[0] in ("英文版期刊", "高校学报") and len(cats) > 1:
        return cats[1]
    return cats[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-11-23")
    args = parser.parse_args()

    coverage_path = CORE / f"core-coverage-{args.date}.csv"
    with coverage_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    groups = Counter()
    details = defaultdict(Counter)
    unmapped = Counter()
    for row in rows:
        primary = primary_category(row.get("categories"))
        name = group(primary)
        groups[name] += 1
        details[name][primary or "(无学科字段)"] += 1
        if name == "未分类" and primary:
            unmapped[primary] += 1

    total = len(rows)
    group_order = [
        "人文社科", "工学", "医药卫生", "理学", "农业科学",
        "综合/交叉", "综合/高校学报", "综合/其他",
        "英文刊（学科未细分）", "未分类",
    ]
    group_order = [name for name in group_order if groups.get(name)]
    for name in groups:
        if name not in group_order:
            group_order.append(name)

    summary_path = CORE / f"core-discipline-summary-{args.date}.csv"
    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["group", "count", "percent"])
        writer.writeheader()
        for name in group_order:
            count = groups[name]
            writer.writerow({
                "group": name,
                "count": count,
                "percent": f"{count / total * 100:.2f}",
            })

    detail_path = CORE / f"core-discipline-detail-{args.date}.csv"
    with detail_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["group", "category", "count", "percent_of_total"])
        writer.writeheader()
        for name in group_order:
            for category, count in details[name].most_common():
                writer.writerow({
                    "group": name,
                    "category": category,
                    "count": count,
                    "percent_of_total": f"{count / total * 100:.2f}",
                })

    work_queue = Counter(row.get("priority") for row in rows)
    languages = Counter(row.get("language") for row in rows)
    lines = [
        f"# 核心期刊学科分布（{args.date}）",
        "",
        f"- 数据源：`journal_catalog/core/core-coverage-{args.date}.csv`",
        f"- 核心刊总数：**{total}**（四份名单并集去重）",
        "- 口径：每本刊取一个主学科；`英文版期刊`/`高校学报` 若还有下一级学科，取下一级。",
        "",
        "## 大类分布",
        "",
        "| 大类 | 数量 | 占比 |",
        "|---|---:|---:|",
    ]
    for name in group_order:
        lines.append(f"| {name} | {groups[name]} | {groups[name] / total * 100:.1f}% |")
    lines += [
        "",
        "## 合并口径",
        "",
        f"- 人文社科：{groups['人文社科']}（{groups['人文社科'] / total * 100:.1f}%）",
        f"- 理工合计（工学+理学）：{groups['工学'] + groups['理学']}（"
        f"{(groups['工学'] + groups['理学']) / total * 100:.1f}%）",
        f"- 医药卫生+农业科学：{groups['医药卫生'] + groups['农业科学']}（"
        f"{(groups['医药卫生'] + groups['农业科学']) / total * 100:.1f}%）",
        "",
        "## 主要子学科（每个大类前 12）",
        "",
    ]
    for name in group_order:
        lines += [f"### {name}（{groups[name]}）", "", "| 子学科 | 数量 |", "|---|---:|"]
        for category, count in details[name].most_common(12):
            lines.append(f"| {category} | {count} |")
        lines.append("")

    lines += [
        "## 按补刊工作队列（不是学科分布）",
        "",
        "| 队列 | 数量 | 占比 |",
        "|---|---:|---:|",
    ]
    for name, count in work_queue.most_common():
        lines.append(f"| {name} | {count} | {count / total * 100:.1f}% |")
    lines += [
        "",
        "## 按语言",
        "",
        "| 语言 | 数量 | 占比 |",
        "|---|---:|---:|",
    ]
    for name, count in languages.most_common():
        lines.append(f"| {name} | {count} | {count / total * 100:.1f}% |")
    lines += [
        "",
        "## 说明与限制",
        "",
        "- 四份核心名单的学科分类体系并不统一：北大核心、CSSCI、CSTPCD 各有分类，CSCD 原始文件没有学科字段，所以有 174 本为“未分类”。",
        "- 73 本英文刊只有 `英文版期刊` 标签，没有可用的下位学科，单列为“英文刊（学科未细分）”，不强行猜学科。",
        "- 一本刊可能有多个学科标签；本表每本只取一个主学科，所以百分比合计为 100%。若按全部标签统计，合计会大于 3461。",
        "- `priority` 是补刊工作队列，不是学科：例如部分工科刊因属于北大核心会进入“中文社科核心”队列；已入包刊统一标“已处理”。不要把队列占比当成学科占比。",
        "- 核心名单本身是公开转载/参考转录版，正式引用前仍要用官方或授权版本复核。",
        "",
        f"逐大类：[core-discipline-summary-{args.date}.csv](core-discipline-summary-{args.date}.csv)；"
        f"逐子学科：[core-discipline-detail-{args.date}.csv](core-discipline-detail-{args.date}.csv)。",
    ]
    md_path = CORE / f"core-discipline-distribution-{args.date}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for name in group_order:
        print(f"{name:12s} {groups[name]:4d} {groups[name] / total * 100:5.1f}%")
    print("unmapped", dict(unmapped))
    print("summary", summary_path)
    print("detail", detail_path)
    print("markdown", md_path)


if __name__ == "__main__":
    raise SystemExit(main())
