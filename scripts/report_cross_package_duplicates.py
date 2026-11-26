"""只读扫描各已安装包的数据表，报告规范化后重复的 DOI。

- 仅处理 information_schema 中确实存在 doi 列的表
- DOI 规范化：去掉 https://doi.org/ 等前缀、URL 解码、小写、去首尾空白/标点
- 输出 journal_catalog/core/cross-package-doi-duplicates-YYYY-MM-DD.csv/.md
- 不删除、不修改任何记录；同一 DOI 在多个包各存一条是当前按包独立身份设计的预期结果
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.storage import SAFE_TABLE, PlatformStore

DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
TRIM = " \t\r\n.;,，。；、"
NULL_VALUES = {"", "null", "none", "n/a", "na", "-", "无", "未知"}
OPTIONAL_COLUMNS = ["sys_resource_uid", "resource_uid", "title", "url", "journal_key", "journal_name"]


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = DOI_PREFIX.sub("", text)
    text = unquote(text)
    text = text.strip().strip("<>").strip()
    text = text.strip(TRIM).lower().strip(TRIM)
    if text in NULL_VALUES:
        return None
    return text


def discover_tables(store: PlatformStore) -> list[dict[str, Any]]:
    packages = store.list_packages()
    if not packages:
        return []
    connection = store.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s""",
                (SETTINGS.mysql_database,),
            )
            columns: dict[str, set[str]] = defaultdict(set)
            for row in cursor.fetchall():
                columns[row["TABLE_NAME"]].add(row["COLUMN_NAME"])
    finally:
        connection.close()

    discovered: list[dict[str, Any]] = []
    for package in packages:
        table = package.get("table_name")
        if not table or not SAFE_TABLE.fullmatch(table):
            continue
        available = columns.get(table, set())
        if "doi" not in available:
            continue
        selected = [column for column in OPTIONAL_COLUMNS if column in available]
        discovered.append({
            "package_key": package["package_key"],
            "table_name": table,
            "columns": selected,
        })
    return discovered


def read_doi_rows(store: PlatformStore, table: str, columns: list[str]) -> list[dict[str, Any]]:
    uid_column = "sys_resource_uid" if "sys_resource_uid" in columns else None
    selected = ["doi"] + [column for column in columns if column != "doi"]
    sql = f"SELECT {','.join(f'`{column}`' for column in selected)} FROM `{table}` " \
          "WHERE doi IS NOT NULL AND doi <> ''"
    connection = store.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            rows = list(cursor.fetchall())
    finally:
        connection.close()
    result: list[dict[str, Any]] = []
    for row in rows:
        doi_norm = normalize_doi(row.get("doi"))
        if not doi_norm:
            continue
        result.append({
            "doi_norm": doi_norm,
            "resource_uid": row.get(uid_column) if uid_column else "",
            "title": row.get("title") or "",
            "url": row.get("url") or "",
            "journal_key": row.get("journal_key") or "",
            "journal_name": row.get("journal_name") or "",
        })
    return result


def md_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="跨包 DOI 重复报告（只读）")
    parser.add_argument("--out-dir", default=str(ROOT / "journal_catalog" / "core"),
                        help="输出目录，默认 journal_catalog/core")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="输出文件名日期，默认本地今天")
    args = parser.parse_args()

    store = PlatformStore(SETTINGS)
    tables = discover_tables(store)
    if not tables:
        print("错误：没有找到包含 doi 列的已安装包数据表", file=sys.stderr)
        return 2

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    table_stats: list[dict[str, Any]] = []
    total_rows = 0
    for table in tables:
        rows = read_doi_rows(store, table["table_name"], table["columns"])
        total_rows += len(rows)
        for row in rows:
            row["package_key"] = table["package_key"]
            row["table_name"] = table["table_name"]
            groups[row["doi_norm"]].append(row)
        table_stats.append({
            "package_key": table["package_key"],
            "table_name": table["table_name"],
            "rows": len(rows),
            "unique": len({row["doi_norm"] for row in rows}),
        })

    duplicates = {doi: rows for doi, rows in groups.items() if len(rows) > 1}
    for doi, rows in duplicates.items():
        packages = {row["package_key"] for row in rows}
        for row in rows:
            row["scope"] = "cross_package" if len(packages) > 1 else "same_package"

    ordered_rows = sorted(
        (row for doi in duplicates for row in duplicates[doi]),
        key=lambda row: (-len(duplicates[row["doi_norm"]]), row["doi_norm"],
                         row["package_key"], str(row["resource_uid"])),
    )

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"cross-package-doi-duplicates-{args.date}"
    csv_path = base.with_suffix(".csv")
    md_path = base.with_suffix(".md")

    columns = ["doi_norm", "occurrences", "scope", "package_key", "resource_uid",
               "title", "url", "journal_key", "journal_name"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in ordered_rows:
            writer.writerow({
                "doi_norm": row["doi_norm"],
                "occurrences": len(duplicates[row["doi_norm"]]),
                "scope": row["scope"],
                "package_key": row["package_key"],
                "resource_uid": row["resource_uid"],
                "title": row["title"],
                "url": row["url"],
                "journal_key": row["journal_key"],
                "journal_name": row["journal_name"],
            })

    cross_package = {doi for doi, rows in duplicates.items()
                     if len({row["package_key"] for row in rows}) > 1}
    same_package = set(duplicates) - cross_package
    involved_packages = sorted({row["package_key"] for doi in duplicates for row in duplicates[doi]})
    package_counts = Counter(row["package_key"] for row in ordered_rows)

    lines: list[str] = []
    lines.append(f"# 跨包 DOI 重复报告 {args.date}")
    lines.append("")
    lines.append(f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- 数据库: `{SETTINGS.mysql_database}`（只读扫描）")
    lines.append("- 规范化: 去 `https://doi.org/` 等前缀、URL 解码、小写、去首尾空白/标点")
    lines.append("- 本报告不删除任何记录；同一 DOI 在多个包各存一条是当前按包独立身份设计的预期结果，"
                 "供人工判断是否合并、忽略或改进跨包去重。")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 扫描包/表: {len(tables)}")
    lines.append(f"- DOI 行数: {total_rows}")
    lines.append(f"- 唯一 DOI: {len(groups)}")
    lines.append(f"- 重复 DOI: {len(duplicates)}（跨包 {len(cross_package)}，同包 {len(same_package)}）")
    if duplicates:
        lines.append(f"- 涉及包: {', '.join(involved_packages)}")
        lines.append(f"- 重复记录按包: {', '.join(f'{key}={value}' for key, value in package_counts.most_common())}")
    else:
        lines.append("- 涉及包: 无（未发现重复 DOI）")
    lines.append("")
    lines.append("## 扫描明细")
    lines.append("")
    lines.append("| package | table | DOI 行数 | 唯一 DOI |")
    lines.append("|---|---|---:|---:|")
    for stat in table_stats:
        lines.append(f"| {stat['package_key']} | {stat['table_name']} | {stat['rows']} | {stat['unique']} |")
    lines.append("")
    lines.append("## 重复示例（最多 50 组，完整明细见 CSV）")
    lines.append("")
    if duplicates:
        lines.append("| DOI | 次数 | 范围 | 包 | 期刊 | 标题 |")
        lines.append("|---|---:|---|---|---|---|")
        for doi in sorted(duplicates, key=lambda value: (-len(duplicates[value]), value))[:50]:
            rows = duplicates[doi]
            for index, row in enumerate(rows):
                lines.append(
                    f"| {md_cell(doi if index == 0 else '')} | "
                    f"{len(rows) if index == 0 else ''} | {row['scope']} | "
                    f"{row['package_key']} | {md_cell(row['journal_name'])} | {md_cell(row['title'])[:80]} |"
                )
    else:
        lines.append("未发现重复 DOI。")
    lines.append("")
    lines.append("## 说明")
    lines.append("")
    lines.append("- 同一 DOI 在不同包分别入库属于预期设计：各包 identity_fields 与数据表相互独立，"
                 "重复报告只用于人工评估，不自动删除。")
    lines.append("- 同一包内出现重复 DOI 更值得关注，通常意味着该包 identity_fields 未包含 DOI，"
                 "或站点 article id 不稳定。")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"CSV: {csv_path}")
    print(f"MD : {md_path}")
    print(f"扫描 {len(tables)} 个包表，DOI 行 {total_rows}，唯一 {len(groups)}，"
          f"重复 {len(duplicates)}（跨包 {len(cross_package)}，同包 {len(same_package)}）")
    if involved_packages:
        print(f"涉及包: {', '.join(involved_packages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
