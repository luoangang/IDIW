"""按 run 汇总每本目标期刊的抓取结果：ok / zero / failed。

数据全部只读：
- package_runs：request_snapshot_json（journal_keys）、work_dir、result_json、status、error_code、error_message
- <work_dir>/output/items.jsonl：按 journal_key 统计条数
- result_json.warnings：`journal_key (名称): 错误` 字符串或 dict

输出（默认 journal_catalog/core）：
- run-journals-<run>-YYYY-MM-DD.csv（utf-8-sig，逐刊）
- run-journals-<run>-YYYY-MM-DD.md（汇总）
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
from crawler_platform.storage import PlatformStore, json_load

TERMINAL_FAILED = {"failed", "timed_out", "cancelled"}
PENDING = {"queued", "running"}
JOURNAL_KEY = re.compile(r"^[0-9A-Za-z_-]{3,64}$")
WARNING_WITH_NAME = re.compile(r"^\s*([0-9A-Za-z_-]{3,64})\s*[（(]([^\n]*?)[）)]\s*[:：]\s*(.+)$")
WARNING_KEY_ONLY = re.compile(r"^\s*([0-9A-Za-z_-]{3,64})\s*[:：]\s*(.+)$")


def md_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def classify_error(code: str | None, message: str | None) -> str:
    code_upper = (code or "").upper()
    text = f"{code or ''} {message or ''}"
    lower = text.lower()
    if "TIMEOUT" in code_upper or "timed out" in lower or "timeout" in lower:
        return "TIMEOUT"
    if any(word in lower for word in ("captcha", "access denied", "forbidden", "robots", "blocked")):
        return "BLOCKED"
    if re.search(r"\b403\b", text) and "forbidden" in lower:
        return "BLOCKED"
    if "http error" in lower or re.search(r"\b(400|401|403|404|407|429|500|502|503|504)\b", text):
        return "HTTP"
    if any(word in lower for word in ("urlerror", "connection", "ssl", "name or service", "network is unreachable", "reset by peer")):
        return "NETWORK"
    if any(word in lower for word in ("jsondecode", "parseerror", "expecting value", "decode", "解析", "parse")):
        return "PARSE"
    if code_upper in {"PROCESS_ERROR", "PROTOCOL_ERROR", "PACKAGE_FAILED"}:
        return code_upper
    if code_upper:
        return code_upper
    return "UNKNOWN"


def parse_warnings(result: dict[str, Any]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    warnings = result.get("warnings")
    if not isinstance(warnings, list):
        return parsed
    for warning in warnings:
        key = name = message = None
        if isinstance(warning, dict):
            key = (warning.get("journal_key") or warning.get("key")
                   or warning.get("journal") or warning.get("journal_id"))
            name = warning.get("journal_name") or warning.get("name")
            message = (warning.get("error") or warning.get("message")
                       or warning.get("warning") or warning.get("detail"))
            if message is None:
                message = json.dumps(warning, ensure_ascii=False)
            if not name:
                matched = re.match(
                    r"^(.*?)\s*(?:当期目次请求失败|当期请求失败|详情页无可用摘要|"
                    r"详情页未找到可用摘要|摘要补采失败|详情页请求失败)[：:]\s*(.*)$",
                    str(message or ""),
                )
                if matched:
                    name, message = matched.group(1).strip(), matched.group(2).strip()
            key = str(key) if key else None
        else:
            text = str(warning)
            match = WARNING_WITH_NAME.match(text)
            if match:
                key, name, message = match.group(1), match.group(2).strip(), match.group(3).strip()
            else:
                match = WARNING_KEY_ONLY.match(text)
                if match and JOURNAL_KEY.match(match.group(1)):
                    key, message = match.group(1), match.group(2).strip()
                elif ":" in text or "：" in text:
                    positions = [index for index in (text.find(":"), text.find("：")) if index >= 0]
                    index = min(positions)
                    name, message = text[:index], text[index + 1:]
                    name = name.strip()
                    for suffix in ("当期目次请求失败", "当期请求失败", "详情页无可用摘要",
                                   "详情页未找到可用摘要", "摘要补采失败", "详情页请求失败"):
                        if name.endswith(suffix):
                            name = name[:-len(suffix)].strip()
                            break
                    message = message.strip()
                else:
                    message = text.strip()
        parsed.append({"key": key, "name": name, "message": str(message or "").strip()})
    return parsed


def find_package_dir(package_key: str) -> Path | None:
    direct = ROOT / "crawler_packages" / "academic" / package_key
    if direct.is_dir():
        return direct
    for candidate in (ROOT / "crawler_packages").glob(f"*/{package_key}"):
        if candidate.is_dir():
            return candidate
    return None


def load_catalog(package_key: str) -> tuple[list[str], dict[str, str]]:
    package_dir = find_package_dir(package_key)
    if package_dir is None:
        return [], {}
    path = package_dir / "journals.json"
    if not path.is_file():
        return [], {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return [], {}
    keys: list[str] = []
    names: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("journal_key")
        if not isinstance(key, str) or not key:
            continue
        if key not in names:
            keys.append(key)
        names[key] = str(row.get("name") or names.get(key) or "")
    return keys, names


def read_items(work_dir: str | None) -> tuple[Counter, dict[str, str], int, str | None]:
    """返回 (按 journal_key 计数, key->名称, 无 key 条数, 提示)。"""
    counts: Counter = Counter()
    names: dict[str, str] = {}
    unattributed = 0
    if not work_dir:
        return counts, names, unattributed, "work_dir 缺失"
    path = Path(work_dir) / "output" / "items.jsonl"
    if not path.is_file():
        return counts, names, unattributed, f"items.jsonl 不存在: {path}"
    bad_lines = 0
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                try:
                    item = json.loads(raw)
                except ValueError:
                    bad_lines += 1
                    continue
                if not isinstance(item, dict):
                    bad_lines += 1
                    continue
                key = item.get("journal_key")
                if not key:
                    unattributed += 1
                    continue
                counts[str(key)] += 1
                if item.get("journal_name"):
                    names[str(key)] = str(item["journal_name"])
    except OSError as exc:
        return counts, names, unattributed, f"items.jsonl 读取失败: {exc}"
    note = f"{bad_lines} 行无法解析" if bad_lines else None
    return counts, names, unattributed, note


def analyze_package_run(row: dict[str, Any]) -> dict[str, Any]:
    package_key = row["package_key"]
    request = json_load(row.get("request_snapshot_json"), {})
    params = request.get("parameters") if isinstance(request, dict) else {}
    request_keys = params.get("journal_keys") if isinstance(params, dict) else None
    result = json_load(row.get("result_json"), {})
    if not isinstance(result, dict):
        result = {}

    catalog_keys, catalog_names = load_catalog(package_key)
    counts, item_names, unattributed, items_note = read_items(row.get("work_dir"))
    warnings = parse_warnings(result)

    if isinstance(request_keys, list) and request_keys:
        targets = [str(key) for key in request_keys]
        target_source = "请求指定"
    elif catalog_keys:
        targets = catalog_keys
        target_source = "按全量推断"
    else:
        targets = list(dict.fromkeys([*counts.keys(), *[w["key"] for w in warnings if w["key"]]]))
        target_source = "按 items 推断"
    if not targets:
        targets = ["(无目标期刊)"]
        target_source = "未知"

    names = dict(catalog_names)
    names.update(item_names)
    for warning in warnings:
        if warning["key"] and warning["name"] and warning["key"] not in names:
            names[warning["key"]] = warning["name"]

    warnings_by_key: dict[str, list[str]] = {}
    warnings_by_name: dict[str, list[str]] = {}
    extra_warnings: list[str] = []
    target_set = set(targets)
    name_to_key = {names[key]: key for key in targets if names.get(key)}
    for warning in warnings:
        message = warning["message"]
        key = warning["key"]
        if key not in target_set and key in name_to_key:
            key = name_to_key[key]
        if key and key in target_set:
            warnings_by_key.setdefault(key, []).append(message)
        elif warning["name"] and warning["name"] in name_to_key:
            warnings_by_name.setdefault(warning["name"], []).append(message)
        else:
            extra_warnings.append(
                " ".join(part for part in (key or "", warning["name"] or "", message) if part)
            )

    status = str(row.get("status") or "")
    package_failed = status in TERMINAL_FAILED
    pending = status in PENDING
    error_obj = result.get("error")
    if not isinstance(error_obj, dict):
        error_obj = {}
    package_error = row.get("error_message") or error_obj.get("message") or ""
    package_code = row.get("error_code") or error_obj.get("code") or ""

    rows: list[dict[str, Any]] = []
    for key in targets:
        name = names.get(key, "")
        items = int(counts.get(key, 0))
        matched = warnings_by_key.get(key, [])
        if not matched and name:
            matched = warnings_by_name.get(name, [])
        if package_failed:
            final = "failed"
            category = classify_error(str(package_code), str(package_error))
            error = str(package_error or package_code or f"package status={status}")
        elif items > 0:
            final = "ok"
            category = ""
            error = ""
        elif matched:
            final = "failed"
            error = "; ".join(matched)
            category = classify_error("", error)
        elif pending:
            final = "pending"
            category = ""
            error = f"package status={status}，尚未产出结果"
        else:
            final = "zero"
            category = "NO_ITEMS"
            error = "未返回条目，且无警告"
        rows.append({
            "run": row["run_id"],
            "package": package_key,
            "journal_key": key,
            "journal_name": name,
            "items": items,
            "status": final,
            "error_category": category,
            "error": error,
            "target_source": target_source,
        })

    return {
        "run_id": row["run_id"],
        "package_key": package_key,
        "package_status": status,
        "error_code": row.get("error_code"),
        "error_message": row.get("error_message"),
        "fetched": row.get("fetched"),
        "work_dir": row.get("work_dir"),
        "execution_id": row.get("execution_id"),
        "targets": rows,
        "unattributed_items": unattributed,
        "items_note": items_note,
        "extra_warnings": extra_warnings,
        "result": result,
    }


def fetch_rows(store: PlatformStore, run_ids: list[int]) -> list[dict[str, Any]]:
    placeholders = ",".join(["%s"] * len(run_ids))
    connection = store.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT pr.run_id,pr.package_id,p.package_key,pr.attempt_no,pr.execution_id,
                pr.status,pr.fetched,pr.inserted,pr.unchanged,pr.rejected,
                pr.request_snapshot_json,pr.result_json,pr.work_dir,
                pr.error_code,pr.error_message,pr.started_at,pr.finished_at
                FROM package_runs pr JOIN crawler_packages p ON p.id=pr.package_id
                WHERE pr.run_id IN ({placeholders}) ORDER BY pr.run_id,pr.package_id,pr.attempt_no""",
                tuple(run_ids),
            )
            rows = list(cursor.fetchall())
            cursor.execute(
                f"""SELECT id,status,started_at,finished_at,error_message
                FROM monitor_runs WHERE id IN ({placeholders}) ORDER BY id""",
                tuple(run_ids),
            )
            runs = list(cursor.fetchall())
    finally:
        connection.close()
    # 同一 run/package 有重试时，仅保留最后一次 attempt。
    latest: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        key = (int(row["run_id"]), row["package_key"])
        current = latest.get(key)
        if current is None or (row["attempt_no"], row["package_id"]) >= (current["attempt_no"], current["package_id"]):
            latest[key] = row
    ordered = [latest[key] for key in sorted(latest)]
    return ordered, runs


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = ["run", "package", "journal_key", "journal_name", "items",
               "status", "error_category", "error", "target_source"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, run_ids: list[int], analyses: list[dict[str, Any]],
                   run_meta: dict[int, dict[str, Any]], generated: str) -> None:
    all_rows = [target for analysis in analyses for target in analysis["targets"]]
    lines: list[str] = []
    lines.append(f"# 运行期刊结果报告 {generated}")
    lines.append("")
    lines.append(f"- run: {', '.join(str(value) for value in run_ids)}")
    lines.append(f"- 生成时间: {generated}")
    lines.append("- 数据源: 平台数据库 `package_runs` + 各 run 的 `output/items.jsonl`")
    lines.append("- 状态定义: `ok`=items>0；`failed`=命中警告或整包 failed/timed_out；"
                 "`zero`=0 条且无警告；`pending`=包仍 queued/running")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append("| run | 包级状态 | 目标刊 | ok | zero | failed | pending | 按全量推断 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for run_id in run_ids:
        rows = [row for row in all_rows if row["run"] == run_id]
        counts = Counter(row["status"] for row in rows)
        status = (run_meta.get(run_id) or {}).get("status") or "unknown"
        inferred = sum(1 for row in rows if row["target_source"] != "请求指定")
        lines.append(
            f"| {run_id} | {status} | {len(rows)} | {counts.get('ok', 0)} | "
            f"{counts.get('zero', 0)} | {counts.get('failed', 0)} | "
            f"{counts.get('pending', 0)} | {inferred} |"
        )
    lines.append("")

    lines.append("## 错误分类计数")
    lines.append("")
    lines.append("| run | error_category | 数量 |")
    lines.append("|---|---|---:|")
    category_rows = Counter(
        (row["run"], row["error_category"])
        for row in all_rows if row["status"] == "failed" and row["error_category"]
    )
    if category_rows:
        for (run_id, category), count in sorted(category_rows.items()):
            lines.append(f"| {run_id} | {category} | {count} |")
    else:
        lines.append("| - | 无失败 | 0 |")
    lines.append("")

    lines.append("## 包级状态")
    lines.append("")
    lines.append("| run | package | status | fetched | error_code | execution_id | error |")
    lines.append("|---|---|---|---:|---|---|---|")
    for analysis in analyses:
        lines.append(
            f"| {analysis['run_id']} | {analysis['package_key']} | {analysis['package_status']} | "
            f"{analysis['fetched']} | {md_cell(analysis['error_code'])} | "
            f"{md_cell(analysis['execution_id'])} | {md_cell(analysis['error_message'])} |"
        )
    lines.append("")

    lines.append("## 失败与 0 条明细")
    lines.append("")
    problem_rows = [row for row in all_rows if row["status"] in {"failed", "zero", "pending"}]
    if problem_rows:
        lines.append("| run | package | journal_key | journal_name | items | status | category | error |")
        lines.append("|---|---|---|---|---:|---|---|---|")
        for row in problem_rows:
            lines.append(
                f"| {row['run']} | {row['package']} | {row['journal_key']} | "
                f"{md_cell(row['journal_name'])} | {row['items']} | {row['status']} | "
                f"{md_cell(row['error_category'])} | {md_cell(row['error'])} |"
            )
    else:
        lines.append("无：所有目标期刊均有产出。")
    lines.append("")

    extras = [analysis for analysis in analyses if analysis["unattributed_items"] or analysis["extra_warnings"]]
    if extras:
        lines.append("## 其他提示")
        lines.append("")
        for analysis in extras:
            if analysis["unattributed_items"]:
                lines.append(
                    f"- run {analysis['run_id']} / {analysis['package_key']}: "
                    f"{analysis['unattributed_items']} 条 items 缺少 journal_key"
                )
            for warning in analysis["extra_warnings"]:
                lines.append(
                    f"- run {analysis['run_id']} / {analysis['package_key']}: "
                    f"未能归属到目标刊的警告：{md_cell(warning)}"
                )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="按 run 输出逐刊 ok/zero/failed 报告（只读）")
    parser.add_argument("--run-id", type=int, action="append", required=True,
                        help="run id，可重复：--run-id 8 --run-id 9")
    parser.add_argument("--out-dir", default=str(ROOT / "journal_catalog" / "core"),
                        help="输出目录，默认 journal_catalog/core")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="输出文件名日期，默认本地今天")
    args = parser.parse_args()

    run_ids = list(dict.fromkeys(args.run_id))
    store = PlatformStore(SETTINGS)
    package_rows, run_rows = fetch_rows(store, run_ids)
    if not package_rows:
        print(f"错误：run {run_ids} 在 package_runs 中没有记录", file=sys.stderr)
        return 2

    analyses = [analyze_package_run(row) for row in package_rows]
    run_meta = {int(row["id"]): row for row in run_rows}
    for run_id in run_ids:
        if run_id not in run_meta:
            print(f"[提示] monitor_runs 中找不到 run {run_id}", file=sys.stderr)

    all_rows = [target for analysis in analyses for target in analysis["targets"]]
    for analysis in analyses:
        notes = []
        if analysis["items_note"]:
            notes.append(analysis["items_note"])
        if analysis["unattributed_items"]:
            notes.append(f"{analysis['unattributed_items']} 条无 journal_key")
        if notes:
            print(f"[提示] run {analysis['run_id']} / {analysis['package_key']}: {'；'.join(notes)}")

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    label = "-".join(str(value) for value in run_ids)
    csv_path = out_dir / f"run-journals-{label}-{args.date}.csv"
    md_path = out_dir / f"run-journals-{label}-{args.date}.md"
    write_csv(csv_path, all_rows)
    write_markdown(md_path, run_ids, analyses, run_meta, datetime.now().strftime("%Y-%m-%d %H:%M"))

    counts = Counter(row["status"] for row in all_rows)
    print(f"CSV: {csv_path}")
    print(f"MD : {md_path}")
    print(f"目标刊 {len(all_rows)}：ok={counts.get('ok', 0)} zero={counts.get('zero', 0)} "
          f"failed={counts.get('failed', 0)} pending={counts.get('pending', 0)}")
    for row in all_rows:
        if row["status"] == "failed":
            print(f"  FAILED run={row['run']} {row['package']} {row['journal_key']} "
                  f"{row['journal_name']} [{row['error_category']}] {row['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
