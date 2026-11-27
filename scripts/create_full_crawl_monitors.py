"""按「每日全量」计划分批创建 manual 监控任务（默认只创建，不执行、不建 daily）。

一个平台 monitor 的 monitor_packages 对同一包只有一行，因此每个包按
journals.json 的 journal_key 切成多批，每批单独创建一个 manual monitor。
默认安全行为：不自动入队、不创建定时任务；--dry-run 只打印计划不写库。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.protocol import validate_parameters
from crawler_platform.storage import PlatformStore, monitor_name_key

ACADEMIC = ROOT / "crawler_packages" / "academic"
QUERY = "最新一期"

DEFAULT_PACKAGES = [
    "cnki_cbpt",
    "custom_toc_journals",
    "magetech_journals",
    "qinyun_journals",
    "rhzh_journals",
    "founder_journals",
    "paperonce_journals",
    "oa_rss_journals",
    "vsb_journals",
    "hep_mirror_journals",
    "sancai_journals",
    "sciengine_journals",
]

# 只在 manifest parameters_schema 支持时写入，避免 additionalProperties=false 报错。
CONFIG_DEFAULTS: list[tuple[str, Any]] = [
    ("collect_mode", "latest_issue"),
    ("per_journal_limit", 2),
    ("timeout_seconds", 15),
    ("enrich_abstract", False),
    ("abstract_enrich_limit", 0),
    ("request_delay_ms", 0),
    ("follow_latest", True),
]

# DOI/检索型包不属于「按期刊当期目录」全量，默认不纳入；即使显式传入也提示并跳过。
NON_TOC_PACKAGES = {
    "flagship_journals": "旗舰 DOI/检索型包，无 journals.json 当期目录",
    "supplement_journals": "补采 DOI/OpenAlex 检索型包，不走当期目录语义",
}


def parse_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期必须是 YYYY-MM-DD") from exc
    return value


def parse_per_batch(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--per-batch 必须是整数") from exc
    if not 1 <= number <= 200:
        raise argparse.ArgumentTypeError("--per-batch 必须在 1-200 之间")
    return number


def load_package(package_key: str) -> dict[str, Any]:
    """读取仓库内 manifest/journals，返回批次规划（不碰数据库）。"""
    if package_key in NON_TOC_PACKAGES:
        return {
            "package_key": package_key,
            "error": f"{NON_TOC_PACKAGES[package_key]}；不按 latest_issue 切批，已跳过",
            "unsupported": True,
        }
    package_dir = ACADEMIC / package_key
    manifest_path = package_dir / "manifest.json"
    journals_path = package_dir / "journals.json"
    if not manifest_path.is_file():
        return {"package_key": package_key, "error": f"manifest 不存在: {manifest_path}"}
    if not journals_path.is_file():
        return {"package_key": package_key, "error": f"journals.json 不存在: {journals_path}"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    properties = manifest["parameters_schema"].get("properties", {})
    if "collect_mode" not in properties:
        return {
            "package_key": package_key,
            "error": "manifest 未声明 collect_mode，无法按 latest_issue 全量切批；已跳过",
            "unsupported": True,
            "manifest_version": manifest.get("package_version"),
        }
    if "latest_issue" not in (properties["collect_mode"].get("enum") or []):
        return {
            "package_key": package_key,
            "error": "manifest 的 collect_mode 不支持 latest_issue；已跳过",
            "unsupported": True,
            "manifest_version": manifest.get("package_version"),
        }

    rows = json.loads(journals_path.read_text(encoding="utf-8"))
    journal_schema = properties.get("journal_keys", {})
    item_schema = journal_schema.get("items", {}) if isinstance(journal_schema, dict) else {}
    min_length = int(item_schema.get("minLength", 1))
    max_length = int(item_schema.get("maxLength", 64))
    valid_keys: list[str] = []
    invalid: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("journal_key")
        name = str(row.get("name") or "")
        if not isinstance(key, str) or not min_length <= len(key) <= max_length:
            invalid.append((str(key), name))
            continue
        if key in seen:
            continue
        seen.add(key)
        valid_keys.append(key)

    if not valid_keys:
        return {"package_key": package_key, "error": "journals.json 中没有可用的 journal_key"}

    max_items = journal_schema.get("maxItems")
    return {
        "package_key": package_key,
        "manifest": manifest,
        "properties": properties,
        "valid_keys": valid_keys,
        "invalid": invalid,
        "max_items": int(max_items) if isinstance(max_items, int) else None,
    }


def build_config(properties: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    config: dict[str, Any] = {"journal_keys": keys}
    for name, value in CONFIG_DEFAULTS:
        if name in properties:
            config[name] = value
    return config


def build_plan(packages: list[str], per_batch: int, date: str, prefix: str) -> tuple[list[dict], list[dict]]:
    batches: list[dict] = []
    skipped: list[dict] = []
    for package_key in packages:
        package = load_package(package_key)
        if package.get("error"):
            skipped.append(package)
            continue
        keys = package["valid_keys"]
        cap = package["max_items"] or per_batch
        size = max(1, min(per_batch, cap, len(keys)))
        chunks = [keys[index:index + size] for index in range(0, len(keys), size)]
        total = len(chunks)
        settings = []
        for number, chunk in enumerate(chunks, 1):
            name = f"{prefix}-{date}-{package_key}-{number:02d}of{total:02d}"
            config = build_config(package["properties"], chunk)
            settings.append({
                "name": name,
                "package_key": package_key,
                "config": config,
                "item_limit": min(10000, max(1, len(chunk) * 2)),
                "count": len(chunk),
            })
        batches.append({
            "package_key": package_key,
            "manifest_version": package["manifest"].get("package_version"),
            "total_keys": len(keys) + len(package["invalid"]),
            "valid_keys": len(keys),
            "invalid": package["invalid"],
            "max_items": package["max_items"],
            "batch_size": size,
            "batch_count": total,
            "limited_by_cap": bool(package["max_items"]) and package["max_items"] < per_batch
                              and len(keys) > package["max_items"],
            "batches": settings,
            "has_per_journal_limit": "per_journal_limit" in package["properties"],
        })
    return batches, skipped


def print_plan(batches: list[dict], skipped: list[dict], per_batch: int, date: str,
               prefix: str, dry_run: bool) -> None:
    mode = "DRY-RUN（只打印，不写库）" if dry_run else "创建计划"
    print(f"== {mode} ==  日期={date}  前缀={prefix}  每批上限={per_batch}")
    header = f"{'包':24s} {'总刊':>5s} {'有效':>5s} {'批数':>4s} {'本批':>4s}  monitor"
    print(header)
    print("-" * len(header))
    for package in batches:
        if package["limited_by_cap"]:
            note = f"（batch 受 manifest maxItems={package['max_items']} 限制）"
        else:
            note = ""
        for index, batch in enumerate(package["batches"], 1):
            print(
                f"{package['package_key']:24s} {package['total_keys']:5d} "
                f"{package['valid_keys']:5d} {package['batch_count']:4d} "
                f"{batch['count']:4d}  {batch['name']}{note if index == 1 else ''}"
            )
    for package in skipped:
        print(f"[跳过] {package['package_key']}: {package.get('error')}")

    print("\n== 备注 ==")
    for package in batches:
        if package["invalid"]:
            preview = "、".join(f"{key or '<空>'} {name}" for key, name in package["invalid"][:6])
            print(
                f"- {package['package_key']} 有 {len(package['invalid'])} 个不符合 journal_keys schema 的 key，"
                f"已跳过：{preview}"
            )
        if not package["has_per_journal_limit"]:
            print(
                f"- {package['package_key']} 的 manifest 不支持 per_journal_limit；"
                f"item_limit={package['batches'][0]['item_limit']}（batch×2）可能不足以容纳整期文章，"
                "若触发 'items exceed request.limit' 请减小 --per-batch。"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="每日全量分批创建 manual 监控任务（默认不入队）")
    parser.add_argument("--packages", nargs="+", default=DEFAULT_PACKAGES,
                        help="包 key 列表；默认 12 个国内包")
    parser.add_argument("--per-batch", type=parse_per_batch, default=100,
                        help="每批期刊数（1-200，默认 100）")
    parser.add_argument("--date", type=parse_date, default=datetime.now().strftime("%Y-%m-%d"),
                        help="名称中的日期，默认本地今天")
    parser.add_argument("--name-prefix", default="每日全量", help="monitor 名称前缀")
    parser.add_argument("--enqueue", action="store_true", help="创建后立即入队执行（默认只创建）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写数据库")
    args = parser.parse_args()

    if args.dry_run and args.enqueue:
        parser.error("--dry-run 与 --enqueue 不能同时使用")

    batches, skipped = build_plan(args.packages, args.per_batch, args.date, args.name_prefix)
    print_plan(batches, skipped, args.per_batch, args.date, args.name_prefix, args.dry_run)

    if not batches:
        print("\n错误：没有可创建批次的包。", file=sys.stderr)
        return 3

    planned_names = [batch["name"] for package in batches for batch in package["batches"]]
    try:
        planned_by_key = {monitor_name_key(name): name for name in planned_names}
    except ValueError as exc:
        print(f"\n错误：monitor 名称不合法：{exc}", file=sys.stderr)
        return 3
    if len(planned_by_key) != len(planned_names):
        print("\n错误：计划内 monitor 名称规范化后重复。", file=sys.stderr)
        return 3

    store = PlatformStore(SETTINGS)
    active_by_key = {monitor_name_key(row["name"]): row["name"]
                     for row in store.list_monitors("active")}
    conflicts = sorted(planned_by_key[key] for key in planned_by_key.keys() & active_by_key.keys())
    if conflicts:
        print("\n错误：以下活动监控任务同名已存在，未创建任何任务：", file=sys.stderr)
        for name in conflicts:
            print(f"  - {name}", file=sys.stderr)
        print("请先归档同名任务，或使用 --date/--name-prefix 区分。", file=sys.stderr)
        return 2

    installed = {row["package_key"]: row for row in store.list_packages()}
    problems: list[str] = []
    for package in batches:
        package_key = package["package_key"]
        installed_row = installed.get(package_key)
        if installed_row is None:
            problems.append(f"{package_key}: 未安装")
            continue
        if installed_row["status"] != "ready":
            problems.append(f"{package_key}: 状态为 {installed_row['status']}，不是 ready")
            continue
        manifest = store.package(installed_row["id"])["manifest"]
        if package["manifest_version"] != installed_row.get("active_version"):
            print(
                f"[提示] {package_key} 仓库 manifest={package['manifest_version']}，"
                f"已安装版本={installed_row.get('active_version')}；按已安装 schema 预校验。"
            )
        for batch in package["batches"]:
            try:
                validate_parameters(manifest["parameters_schema"], batch["config"])
            except Exception as exc:
                problems.append(f"{package_key}/{batch['name']}: 参数不被已安装包接受：{exc}")
    if problems:
        print("\n错误：预校验失败，未创建任何任务：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 3

    if args.dry_run:
        print(f"\nDRY-RUN 完成：计划创建 {len(planned_names)} 个 manual monitor，未写数据库。")
        return 0

    created: list[tuple[str, int]] = []
    try:
        for package in batches:
            for batch in package["batches"]:
                monitor_id = store.create_monitor(
                    name=batch["name"],
                    query=QUERY,
                    aliases=[],
                    categories=[],
                    package_keys=[package["package_key"]],
                    schedule_type="manual",
                    package_settings=[{
                        "package_key": package["package_key"],
                        "enabled": True,
                        "item_limit": batch["item_limit"],
                        "config": batch["config"],
                    }],
                )
                created.append((batch["name"], monitor_id))
                print(f"created monitor_id={monitor_id} name={batch['name']}")
    except Exception as exc:
        print(f"\n错误：创建中断（{type(exc).__name__}: {exc}）。已创建 {len(created)} 个：", file=sys.stderr)
        for name, monitor_id in created:
            print(f"  - {monitor_id} {name}", file=sys.stderr)
        print("已创建的任务未删除，请人工核对；重复运行前先归档或改名。", file=sys.stderr)
        return 4

    print(f"\n完成：创建 {len(created)} 个 manual monitor。")
    if args.enqueue:
        enqueued: list[tuple[str, int, int]] = []
        try:
            for name, monitor_id in created:
                run_id = store.enqueue_monitor(monitor_id)
                enqueued.append((name, monitor_id, run_id))
                print(f"enqueued monitor_id={monitor_id} run_id={run_id} name={name}")
        except Exception as exc:
            print(
                f"\n错误：入队中断（{type(exc).__name__}: {exc}）。"
                f"已入队 {len(enqueued)}/{len(created)} 个：",
                file=sys.stderr,
            )
            for name, monitor_id, run_id in enqueued:
                print(f"  - run_id={run_id} monitor_id={monitor_id} {name}", file=sys.stderr)
            print("未入队的 monitor 仍保留，可在网页端补入队；不要重复运行本脚本。", file=sys.stderr)
            return 5
    else:
        print("未入队（默认）。需要执行时加 --enqueue，或在网页端逐个入队。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
