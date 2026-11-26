"""身份稳定性审计：读取各已安装包 manifest 的 output_schema.identity_fields。

标记风险：
- identity_fields 缺失 / 不在输出字段中 / 可空或非标量
- 直接使用不稳定字段（url/current_url/journal_url/pdf_url/title/published_at 等）
- 使用期次/年度字段（year/issue/volume）作为身份
- external_id 在爬虫代码中可能回退为文章 URL / 当期 URL 的哈希或路径片段

输出 journal_catalog/core/identity-audit-YYYY-MM-DD.md（附同名 CSV）。
只读，不修改任何包或数据库。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore

FIELD_MEANINGS = {
    "journal_key": "期刊稳定键，由 journals.json 分配",
    "journal_name": "期刊名称，可能调整",
    "external_id": "站点侧文章 ID（接口/查询参数/URL 片段，取决于适配器）",
    "doi": "DOI，论文级稳定标识；缺 DOI 的文章无法入库",
    "source_site": "来源站点标识（baidu/wikipedia/google_news 等）",
    "issn": "ISSN",
    "title": "标题，可能被修订",
    "url": "文章链接，可能带参数、跳转或换域",
    "current_url": "当前期页面链接，每期都会变化",
    "journal_url": "期刊主页链接，可能改版",
    "pdf_url": "PDF 链接",
    "published_at": "发布时间，可能修正",
    "year": "出版年份，随年度变化",
    "issue": "期号，随期次变化",
    "volume": "卷号，随年度变化",
    "pages": "页码，可能随排版变化",
    "authors": "作者，可能修订",
    "abstract": "摘要，可能修订",
    "summary": "简介/摘要，可能修订",
    "content": "正文，可能修订",
    "publisher": "出版方",
    "language": "语种",
    "country": "国家/地区",
    "source_api": "数据来源 API",
    "openalex_id": "OpenAlex 记录 ID",
    "matched_terms": "命中的检索词",
    "affiliations": "作者机构",
    "cited_by_count": "被引次数，会变化",
    "open_access": "开放获取标记",
}

UNSTABLE_FIELDS = {
    "url": "URL 链接可能带参数、跳转或换域",
    "current_url": "当期页面 URL，每期都会变化",
    "journal_url": "期刊主页 URL，可能改版",
    "pdf_url": "PDF 链接可能变化",
    "title": "标题可能被修订",
    "published_at": "发布时间可能被修正",
    "summary": "摘要/简介可能被修订",
    "abstract": "摘要可能被修订",
    "content": "正文可能被修订",
    "authors": "作者信息可能被修订",
}
PERIOD_FIELDS = {
    "year": "年度字段",
    "issue": "期次字段",
    "volume": "卷次字段",
}
URL_TOKENS = ("article_url", "current_url", "journal_url", "urljoin", "href", "canonical", ".split(")


def md_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def url_derived_expression(line: str) -> str | None:
    """仅当 url 出现在 external_id 的赋值/字面量值里时才算 URL 派生。"""
    stripped = line.strip()
    if stripped.startswith("def ") or stripped.startswith("return "):
        return None
    match = re.match(r"^external_id\s*=\s*(.+)$", stripped)
    if match:
        expression = match.group(1)
    elif '"external_id":' in stripped:
        expression = stripped.split('"external_id":', 1)[1]
    else:
        return None
    if any(token in expression for token in URL_TOKENS):
        return expression.strip()
    return None


def field_rank(field: dict[str, Any]) -> str:
    nullable = "可空" if field.get("nullable") else "非空"
    return f"{field.get('type', '?')}, {nullable}"


def package_crawler_path(package: dict[str, Any]) -> Path | None:
    repo = ROOT / "crawler_packages" / str(package.get("category") or "") / package["package_key"] / "crawler.py"
    if repo.is_file():
        return repo
    artifact = package.get("active_artifact_path")
    if artifact:
        candidate = Path(artifact) / "crawler.py"
        if candidate.is_file():
            return candidate
    return None


def scan_external_id_evidence(package: dict[str, Any], identity_fields: list[str]) -> list[str]:
    if "external_id" not in identity_fields:
        return []
    path = package_crawler_path(package)
    if path is None:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    evidence: list[str] = []
    seen: set[str] = set()
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or "external_id" not in stripped:
            continue
        if url_derived_expression(stripped) is None:
            continue
        if stripped in seen:
            continue
        seen.add(stripped)
        evidence.append(f"{path.name}:L{number}: {stripped[:220]}")
        if len(evidence) >= 3:
            break
    return evidence


def repo_manifest_identity(package_key: str, category: str) -> list[str] | None:
    path = ROOT / "crawler_packages" / category / package_key / "manifest.json"
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    identity = (manifest.get("output_schema") or {}).get("identity_fields")
    return list(identity) if isinstance(identity, list) else None


def audit_package(store: PlatformStore, row: dict[str, Any]) -> dict[str, Any]:
    package = store.package(row["id"])
    manifest = package.get("manifest") or {}
    output_schema = manifest.get("output_schema") or {}
    identity = output_schema.get("identity_fields") or []
    if not isinstance(identity, list):
        identity = []
    identity = [str(name) for name in identity]
    fields = {field["name"]: field for field in output_schema.get("fields") or []
              if isinstance(field, dict) and field.get("name")}

    risks: list[dict[str, str]] = []

    if not identity:
        risks.append({"code": "IDENTITY_MISSING", "level": "high",
                      "detail": "manifest 未声明 identity_fields"})
    for name in identity:
        if name not in fields:
            risks.append({"code": "IDENTITY_NOT_IN_FIELDS", "level": "high",
                          "detail": f"identity 字段 {name} 不在 output_schema.fields 中"})
            continue
        field = fields[name]
        if field.get("nullable"):
            risks.append({"code": "IDENTITY_NULLABLE", "level": "high",
                          "detail": f"{name} 可空，空值会造成身份碰撞"})
        if field.get("type") not in {"string", "integer", "decimal", "boolean", "date", "datetime"}:
            risks.append({"code": "IDENTITY_NOT_SCALAR", "level": "high",
                          "detail": f"{name} 类型为 {field.get('type')}，不是标量"})
        if name in UNSTABLE_FIELDS:
            risks.append({"code": "UNSTABLE_FIELD", "level": "high",
                          "detail": f"identity 直接使用 {name}：{UNSTABLE_FIELDS[name]}"})
        if name in PERIOD_FIELDS:
            risks.append({"code": "PERIOD_FIELD", "level": "high",
                          "detail": f"identity 使用 {name}（{PERIOD_FIELDS[name]}），换期/换卷后同一文章身份会漂移"})

    evidence = scan_external_id_evidence(package, identity)
    if evidence:
        risks.append({"code": "URL_DERIVED_EXTERNAL_ID", "level": "medium",
                      "detail": "external_id 存在由文章/当期 URL（或 href/路径片段）派生的路径；"
                                "站点换期、改 URL 结构或加参数时，同一文章可能生成新身份"})

    if identity == ["doi"]:
        risks.append({"code": "DOI_ONLY", "level": "medium",
                      "detail": "仅用 DOI 作为身份；缺 DOI 的文章无法入库，DOI 更正/重复也会影响身份"})

    repo_identity = repo_manifest_identity(package["package_key"], package.get("category") or "")
    if repo_identity is not None and repo_identity != identity:
        risks.append({"code": "REPO_MANIFEST_MISMATCH", "level": "medium",
                      "detail": f"仓库 manifest identity={repo_identity} 与已安装版本 {identity} 不一致"})

    if len(identity) == 1 and identity != ["doi"]:
        risks.append({"code": "SINGLE_FIELD", "level": "low",
                      "detail": "单一字段身份，需确认该字段在站点内全局唯一"})

    levels = {risk["level"] for risk in risks}
    level = "high" if "high" in levels else ("medium" if "medium" in levels else "low")
    meanings = []
    for name in identity:
        field = fields.get(name, {})
        meaning = FIELD_MEANINGS.get(name, "未收录的字段含义，需人工确认")
        meanings.append(f"{name}（{field_rank(field)}）：{meaning}")

    return {
        "package_key": package["package_key"],
        "package_name": package.get("name") or "",
        "version": package.get("active_version") or "",
        "category": package.get("category") or "",
        "identity_fields": identity,
        "identity_count": len(identity),
        "risk_level": level,
        "risk_codes": ",".join(dict.fromkeys(risk["code"] for risk in risks)),
        "risks": "；".join(f"[{risk['level']}] {risk['detail']}" for risk in risks),
        "field_meanings": "；".join(meanings),
        "evidence": " | ".join(evidence),
        "evidence_items": evidence,
        "risk_items": risks,
        "meanings": meanings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="身份字段稳定性审计（只读）")
    parser.add_argument("--out-dir", default=str(ROOT / "journal_catalog" / "core"),
                        help="输出目录，默认 journal_catalog/core")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="输出文件名日期，默认本地今天")
    args = parser.parse_args()

    store = PlatformStore(SETTINGS)
    packages = store.list_packages()
    if not packages:
        print("错误：数据库中没有已安装包", file=sys.stderr)
        return 2

    audits = [audit_package(store, row) for row in packages]
    audits.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}[item["risk_level"]],
                                  item["package_key"]))
    level_counts = Counter(item["risk_level"] for item in audits)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"identity-audit-{args.date}"
    csv_path = base.with_suffix(".csv")
    md_path = base.with_suffix(".md")

    columns = ["package_key", "version", "category", "identity_fields", "identity_count",
               "risk_level", "risk_codes", "risks", "field_meanings", "evidence"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for audit in audits:
            writer.writerow({
                "package_key": audit["package_key"],
                "version": audit["version"],
                "category": audit["category"],
                "identity_fields": ",".join(audit["identity_fields"]),
                "identity_count": audit["identity_count"],
                "risk_level": audit["risk_level"],
                "risk_codes": audit["risk_codes"],
                "risks": audit["risks"],
                "field_meanings": audit["field_meanings"],
                "evidence": audit["evidence"],
            })

    lines: list[str] = []
    lines.append(f"# 身份字段稳定性审计 {args.date}")
    lines.append("")
    lines.append(f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- 数据源: 已安装包 manifest（`crawler_packages.manifest_json`）及仓库中的 crawler.py")
    lines.append("- 平台用 `sha256(json(identity 字段值))` 生成 sys_resource_uid；identity 变化会让同一文章变成新记录。")
    lines.append("- 本报告只读，不修改任何包或数据。")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 包数: {len(audits)}")
    lines.append(f"- 高风险: {level_counts.get('high', 0)}")
    lines.append(f"- 需关注: {level_counts.get('medium', 0)}")
    lines.append(f"- 低风险/稳定: {level_counts.get('low', 0)}")
    lines.append("")
    lines.append("| package | 版本 | identity_fields | 风险 | 主要问题 |")
    lines.append("|---|---|---|---|---|")
    for audit in audits:
        problems = "；".join(f"[{risk['level']}] {risk['detail']}" for risk in audit["risk_items"])
        if not problems:
            problems = "未发现明显风险"
        lines.append(
            f"| {audit['package_key']} | {audit['version']} | "
            f"{', '.join(audit['identity_fields'])} | {audit['risk_level']} | {md_cell(problems)} |"
        )
    lines.append("")

    lines.append("## 逐包明细")
    lines.append("")
    for audit in audits:
        lines.append(f"### {audit['package_key']}（{audit['package_name']}，v{audit['version']}）")
        lines.append("")
        if audit["identity_fields"]:
            lines.append(f"- identity_fields: {', '.join(audit['identity_fields'])}")
        else:
            lines.append("- identity_fields: （缺失）")
        lines.append(f"- 风险等级: {audit['risk_level']}")
        lines.append("- 字段含义:")
        for meaning in audit["meanings"]:
            lines.append(f"  - {meaning}")
        if audit["risk_items"]:
            lines.append("- 风险:")
            for risk in audit["risk_items"]:
                lines.append(f"  - [{risk['level']}] {risk['code']}: {risk['detail']}")
        else:
            lines.append("- 风险: 未发现明显不稳定字段")
        if audit["evidence_items"]:
            lines.append("- 代码证据:")
            for evidence in audit["evidence_items"]:
                lines.append(f"  - `{evidence}`")
        lines.append("")

    lines.append("## 判定说明")
    lines.append("")
    lines.append("- 高风险: identity 缺失/可空/非标量，或直接使用 URL、标题、发布时间、年度/期次等易变字段。")
    lines.append("- 需关注: `external_id` 在代码中存在 URL/路径回退，或仅用 DOI 单一身份；"
                 "正常路径稳定，但兜底路径可能漂移。")
    lines.append("- 低风险: `journal_key` + 站点文章 ID 等稳定复合身份，未发现不稳定字段。")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"CSV: {csv_path}")
    print(f"MD : {md_path}")
    print(f"审计 {len(audits)} 个包：high={level_counts.get('high', 0)} "
          f"medium={level_counts.get('medium', 0)} low={level_counts.get('low', 0)}")
    for audit in audits:
        if audit["risk_level"] != "low":
            print(f"  {audit['risk_level'].upper():6s} {audit['package_key']}: {audit['risk_codes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
