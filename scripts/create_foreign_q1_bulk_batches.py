"""按「国外 Q1」watchlist 分批创建 bulk_window manual 监控任务（默认只创建，不执行）。

数据来源：journal_catalog/foreign/foreign_journals_q1_2026-11-25.csv，
只取 include_daily=yes 的期刊，按行顺序每 --per-batch 本一批，每批一个 manual monitor。
每批使用 foreign_q1_journals >=1.1.0 的 bulk_window 模式：按 bulk_size 个 ISSN 一组
请求 OpenAlex，减少逐刊请求开销，适合全量快速采集。

默认安全行为：
- 不自动入队（--enqueue 才入队）、不创建 daily/定时任务、不常驻；
- --dry-run 只打印计划并写 plan CSV，完全不连接数据库；
- 活动任务同名直接报错，不静默重复；
- 每批期刊数上限 500（500 × per_journal_limit 20 = 10000，即平台 item_limit 上限）。
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.protocol import validate_parameters
from crawler_platform.storage import PlatformStore, monitor_name_key

PACKAGE_KEY = "foreign_q1_journals"
QUERY = "最新一期"
MIN_PACKAGE_VERSION = (1, 1, 0)
MAX_ITEM_LIMIT = 10000
MAX_PER_BATCH = 500
DEFAULT_WATCHLIST = ROOT / "journal_catalog" / "foreign" / "foreign_journals_q1_2026-11-25.csv"
DEFAULT_PLAN_OUT = ROOT / "journal_catalog" / "foreign" / "foreign_q1_bulk_batches_2026-11-25.csv"

PLAN_HEADER = [
    "batch_name",
    "package_key",
    "journals",
    "item_limit",
    "monitor_id",
    "first_journal",
    "last_journal",
]


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
    if not 1 <= number <= MAX_PER_BATCH:
        raise argparse.ArgumentTypeError(
            f"--per-batch 必须在 1-{MAX_PER_BATCH} 之间"
            f"（{MAX_PER_BATCH}×每刊上限 20={MAX_ITEM_LIMIT}，受平台 item_limit 上限约束）"
        )
    return number


def parse_per_journal_limit(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--per-journal-limit 必须是整数") from exc
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("--per-journal-limit 必须在 1-100 之间（包参数上限）")
    return number


def parse_bulk_size(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--bulk-size 必须是整数") from exc
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("--bulk-size 必须在 1-100 之间")
    return number


def parse_lookback_days(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--lookback-days 必须是整数") from exc
    if not 1 <= number <= 90:
        raise argparse.ArgumentTypeError("--lookback-days 必须在 1-90 之间（包参数上限）")
    return number


def version_tuple(value: Any) -> tuple[int, ...] | None:
    match = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)", str(value or ""))
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def load_watchlist(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """读取 watchlist，返回 include_daily=yes 的期刊（按文件行顺序、journal_id 去重）与统计。"""
    if not path.is_file():
        raise FileNotFoundError(f"watchlist 不存在: {path}")
    rows: list[dict[str, str]] = []
    total = 0
    excluded = 0
    invalid: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = {"include_daily", "journal_id", "title"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"watchlist 缺少列: {sorted(missing)}")
        for row in reader:
            total += 1
            if (row.get("include_daily") or "").strip().lower() != "yes":
                excluded += 1
                continue
            key = (row.get("journal_id") or "").strip()
            title = (row.get("title") or "").strip()
            if not key:
                invalid.append(title or f"<第 {total} 条>")
                continue
            if key in seen:
                duplicates.append(key)
                continue
            seen.add(key)
            rows.append({"key": key, "name": title or key})
    stats = {
        "total": total,
        "excluded": excluded,
        "included": len(rows),
        "invalid": invalid,
        "duplicate_keys": duplicates,
    }
    return rows, stats


def build_plan(rows: list[dict[str, str]], per_batch: int, date: str, prefix: str,
               per_journal_limit: int = 20, bulk_size: int = 100,
               lookback_days: int = 30) -> list[dict[str, Any]]:
    chunks = [rows[index:index + per_batch] for index in range(0, len(rows), per_batch)]
    total = len(chunks)
    width = len(str(total))
    plan: list[dict[str, Any]] = []
    for number, chunk in enumerate(chunks, 1):
        keys = [row["key"] for row in chunk]
        expected = len(chunk) * per_journal_limit
        plan.append({
            "name": f"{prefix}-{date}-{number:0{width}d}of{total:0{width}d}",
            "package_key": PACKAGE_KEY,
            "config": {
                "journal_keys": keys,
                "collect_mode": "bulk_window",
                "bulk_size": bulk_size,
                "lookback_days": lookback_days,
                "per_journal_limit": per_journal_limit,
                "timeout_seconds": 120,
                "require_abstract": False,
            },
            "item_limit": min(MAX_ITEM_LIMIT, expected),
            "expected": expected,
            "count": len(chunk),
            "first_journal": chunk[0]["name"],
            "last_journal": chunk[-1]["name"],
        })
    return plan


def write_plan_csv(plan: list[dict[str, Any]], path: Path,
                   monitor_ids: dict[str, int] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = monitor_ids or {}
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(PLAN_HEADER)
        for batch in plan:
            writer.writerow([
                batch["name"],
                batch["package_key"],
                batch["count"],
                batch["item_limit"],
                ids.get(batch["name"], ""),
                batch["first_journal"],
                batch["last_journal"],
            ])


def print_plan(plan: list[dict[str, Any]], stats: dict[str, Any], per_batch: int,
               per_journal_limit: int, bulk_size: int, lookback_days: int,
               date: str, prefix: str, watchlist: Path, plan_out: Path,
               dry_run: bool) -> None:
    mode = "DRY-RUN（只打印 + 写 plan CSV，不连数据库）" if dry_run else "创建计划"
    print(f"== {mode} ==")
    print(f"watchlist={watchlist}")
    print(
        f"日期={date}  前缀={prefix}  包={PACKAGE_KEY}  collect_mode=bulk_window  "
        f"每批={per_batch}  每刊上限={per_journal_limit}  bulk_size={bulk_size}  "
        f"回溯={lookback_days} 天"
    )
    print(
        f"watchlist 总行={stats['total']}  include_daily≠yes 跳过={stats['excluded']}  "
        f"有效期刊={stats['included']}  批数={len(plan)}"
    )
    print(f"plan CSV={plan_out}")
    if stats["invalid"]:
        preview = "、".join(stats["invalid"][:6])
        print(f"[提示] {len(stats['invalid'])} 条 include_daily=yes 记录缺少 journal_id，已跳过：{preview}")
    if stats["duplicate_keys"]:
        preview = "、".join(stats["duplicate_keys"][:6])
        print(f"[提示] {len(stats['duplicate_keys'])} 个重复 journal_id 已去重（保留首次出现）：{preview}")

    print("\n== 批次一览 ==")
    header = f"{'批次':44s} {'本数':>4s} {'item_limit':>10s}  首刊 → 末刊"
    print(header)
    print("-" * (len(header) + 8))
    total = len(plan)
    if total <= 12:
        shown = list(range(total))
    else:
        shown = [0, 1, 2, total - 3, total - 2, total - 1]
    last_index = -1
    for index in shown:
        batch = plan[index]
        if index - last_index > 1:
            print(f"{'...':44s} {'...':>4s} {'...':>10s}")
        print(
            f"{batch['name']:44s} {batch['count']:4d} {batch['item_limit']:10d}  "
            f"{batch['first_journal']} → {batch['last_journal']}"
        )
        last_index = index
    if total:
        covered = sum(batch["count"] for batch in plan)
        print(
            f"\n合计 {total} 批 / {covered} 本；"
            f"item_limit = min({MAX_ITEM_LIMIT}, 本批本数 × {per_journal_limit})。"
        )
        capped = [batch for batch in plan if batch["expected"] > MAX_ITEM_LIMIT]
        if capped:
            print(
                f"[提示] {len(capped)} 批的理论条数超过 {MAX_ITEM_LIMIT}，"
                f"item_limit 已截断；如需每刊足额 {per_journal_limit} 条，请减小 --per-batch。"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "国外 Q1 watchlist 分批创建 bulk_window manual 监控任务"
            "（默认只创建、不入队；--dry-run 不连数据库）"
        )
    )
    parser.add_argument("--per-batch", type=parse_per_batch, default=500,
                        help=f"每批期刊数（1-{MAX_PER_BATCH}，默认 500；上限受 item_limit 10000 约束）")
    parser.add_argument("--per-journal-limit", type=parse_per_journal_limit, default=20,
                        help="每刊最多返回条数（1-100，默认 20）")
    parser.add_argument("--bulk-size", type=parse_bulk_size, default=100,
                        help="bulk_window 每组 ISSN 数（1-100，默认 100）")
    parser.add_argument("--lookback-days", type=parse_lookback_days, default=30,
                        help="回溯天数（1-90，默认 30）")
    parser.add_argument("--date", type=parse_date, default=datetime.now().strftime("%Y-%m-%d"),
                        help="名称中的日期，默认本地今天")
    parser.add_argument("--name-prefix", default="国外Q1-bulk", help="monitor 名称前缀")
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST,
                        help="Q1 watchlist CSV 路径")
    parser.add_argument("--plan-out", type=Path, default=DEFAULT_PLAN_OUT,
                        help="批次计划 CSV 输出路径")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印计划并写 plan CSV，不连接数据库")
    parser.add_argument("--enqueue", action="store_true",
                        help="创建后立即入队执行（默认只创建）")
    args = parser.parse_args(argv)

    if args.dry_run and args.enqueue:
        parser.error("--dry-run 与 --enqueue 不能同时使用")

    try:
        rows, stats = load_watchlist(args.watchlist)
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 3

    plan = build_plan(
        rows, args.per_batch, args.date, args.name_prefix,
        per_journal_limit=args.per_journal_limit,
        bulk_size=args.bulk_size,
        lookback_days=args.lookback_days,
    )
    print_plan(
        plan, stats, args.per_batch, args.per_journal_limit, args.bulk_size,
        args.lookback_days, args.date, args.name_prefix, args.watchlist,
        args.plan_out, args.dry_run,
    )

    if not plan:
        print("\n错误：include_daily=yes 的期刊为空，没有可创建的批次。", file=sys.stderr)
        return 3

    try:
        planned_by_key = {monitor_name_key(batch["name"]): batch["name"] for batch in plan}
    except ValueError as exc:
        print(f"\n错误：monitor 名称不合法：{exc}", file=sys.stderr)
        return 3
    if len(planned_by_key) != len(plan):
        print("\n错误：计划内 monitor 名称规范化后重复（检查 --date/--name-prefix）。", file=sys.stderr)
        return 3

    if args.dry_run:
        write_plan_csv(plan, args.plan_out)
        print(
            f"\nDRY-RUN 完成：计划创建 {len(plan)} 个 manual monitor（bulk_window），"
            "未连接数据库、未写 monitors 表、未入队。"
        )
        print("注意：dry-run 未校验同名活动任务、包版本与参数 schema；实际创建时会先校验。")
        return 0

    store = PlatformStore(SETTINGS)
    try:
        active_by_key = {monitor_name_key(row["name"]): row["name"]
                         for row in store.list_monitors("active")}
        conflicts = sorted(planned_by_key[key] for key in planned_by_key.keys() & active_by_key.keys())
        if conflicts:
            print("\n错误：以下活动监控任务同名已存在，未创建任何任务：", file=sys.stderr)
            for name in conflicts:
                print(f"  - {name}", file=sys.stderr)
            print("请先归档同名任务，或使用 --date/--name-prefix 区分。", file=sys.stderr)
            return 2

        installed_row = next(
            (row for row in store.list_packages() if row["package_key"] == PACKAGE_KEY), None
        )
        if installed_row is None:
            print(
                f"\n错误：包 {PACKAGE_KEY} 尚未安装。请先导入包（status=ready）再运行本脚本。",
                file=sys.stderr,
            )
            return 3
        if installed_row["status"] != "ready":
            print(
                f"\n错误：包 {PACKAGE_KEY} 状态为 {installed_row['status']}，不是 ready。",
                file=sys.stderr,
            )
            return 3

        installed_version = version_tuple(installed_row.get("active_version"))
        if installed_version is None or installed_version < MIN_PACKAGE_VERSION:
            required = ".".join(str(part) for part in MIN_PACKAGE_VERSION)
            actual = installed_row.get("active_version") or "未知"
            print(
                f"\n错误：已安装的 {PACKAGE_KEY} 版本为 {actual}，"
                f"bulk_window 需要 >= {required}。请先导入新包后再运行。",
                file=sys.stderr,
            )
            return 3

        manifest = store.package(installed_row["id"])["manifest"]
        problems: list[str] = []
        for batch in plan:
            try:
                validate_parameters(manifest["parameters_schema"], batch["config"])
            except Exception as exc:
                problems.append(f"{batch['name']}: 参数不被已安装包接受：{exc}")
        if problems:
            print("\n错误：参数预校验失败，未创建任何任务：", file=sys.stderr)
            for problem in problems[:10]:
                print(f"  - {problem}", file=sys.stderr)
            if len(problems) > 10:
                print(f"  ... 另有 {len(problems) - 10} 条", file=sys.stderr)
            return 3
    except Exception as exc:
        print(f"\n错误：预检失败（{type(exc).__name__}: {exc}）。", file=sys.stderr)
        return 3

    created: list[tuple[str, int]] = []
    try:
        for batch in plan:
            monitor_id = store.create_monitor(
                name=batch["name"],
                query=QUERY,
                aliases=[],
                categories=[],
                package_keys=[PACKAGE_KEY],
                schedule_type="manual",
                package_settings=[{
                    "package_key": PACKAGE_KEY,
                    "enabled": True,
                    "item_limit": batch["item_limit"],
                    "config": batch["config"],
                }],
            )
            created.append((batch["name"], monitor_id))
            print(f"created monitor_id={monitor_id} name={batch['name']}")
    except Exception as exc:
        written = {name: monitor_id for name, monitor_id in created}
        write_plan_csv(plan, args.plan_out, written)
        print(
            f"\n错误：创建中断（{type(exc).__name__}: {exc}）。已创建 {len(created)}/{len(plan)} 个，"
            f"plan CSV 已更新（含已创建 id）：{args.plan_out}",
            file=sys.stderr,
        )
        for name, monitor_id in created:
            print(f"  - {monitor_id} {name}", file=sys.stderr)
        print("已创建的任务未删除，请人工核对；重复运行前先归档或改名。", file=sys.stderr)
        return 4

    write_plan_csv(plan, args.plan_out, {name: monitor_id for name, monitor_id in created})
    print(f"\n完成：创建 {len(created)} 个 manual monitor；plan CSV 已写入 {args.plan_out}")

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
        print("未入队（默认）。需要执行时加 --enqueue，或在网页端分批入队。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
