#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""国外 Q1 全量逐刊采集报告生成器（逐刊 CSV + 自包含 HTML）。

读取平台运行记录（只读）与每个 package execution 的
crawler_platform_runtime/runs/<execution_id>/output/items.jsonl、result.json，
按 journal_key 聚合后输出：

  <out-dir>/<prefix>_journals.csv    5,238 行逐刊汇总（utf-8-sig）
  <out-dir>/<prefix>_report.html     自包含、无 CDN 的可搜索图表报告

若同目录存在 <prefix>_items.csv，页脚会自动链接该文章明细。

只读输入，不联网，不写数据库，不创建任务。
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore

DATA_DIR = ROOT / "journal_catalog" / "foreign"
WATCHLIST_CSV = DATA_DIR / "foreign_journals_q1_2026-11-25.csv"
PACKAGE_JOURNALS_JSON = (
    ROOT / "crawler_packages" / "academic" / "foreign_q1_journals" / "journals.json"
)
PROTECTED_OUTPUTS = {
    WATCHLIST_CSV.resolve(),
    (DATA_DIR / "foreign_q1_report_2026-11-25.html").resolve(),
}
DEFAULT_DATE = "2026-11-26"
EXPECTED_DAILY = 5238

EDITION_ORDER = ["SCIE", "SSCI", "ESCI", "AHCI", "?"]
EDITION_LABEL = {"SCIE": "SCIE", "SSCI": "SSCI", "ESCI": "ESCI", "AHCI": "AHCI", "?": "未标注"}
EDITION_COLOR = {
    "SCIE": "#1d4ed8",
    "SSCI": "#0f766e",
    "ESCI": "#7c3aed",
    "AHCI": "#b45309",
    "?": "#64748b",
}
FREQ_ORDER = [
    "quarterly", "monthly", "bimonthly", "annual", "10ish", "semimonthly",
    "semiannual", "triannual", "5/year", "weekly", "unknown",
]
FREQ_LABEL = {
    "weekly": "周刊",
    "semimonthly": "半月刊",
    "monthly": "月刊",
    "bimonthly": "双月刊",
    "quarterly": "季刊",
    "triannual": "三季刊",
    "semiannual": "半年刊",
    "annual": "年刊",
    "5/year": "5 期/年",
    "10ish": "约 10 期/年",
    "unknown": "频次未知",
}
LOW_FREQ_CLASSES = {"annual", "semiannual", "triannual"}
BATCH_STATUS_LABEL = {
    "completed": "完成",
    "partial": "部分完成",
    "failed": "失败",
    "running": "运行中",
    "missing": "缺失",
    "queued": "排队",
}
BATCH_STATUS_CHIP = {
    "completed": "chip-green",
    "partial": "chip-amber",
    "failed": "chip-red",
    "running": "chip-blue",
    "missing": "chip-gray",
    "queued": "chip-gray",
}
BATCH_COLOR = {
    "completed": "#0f766e",
    "partial": "#b45309",
    "failed": "#b91c1c",
    "running": "#1d4ed8",
    "missing": "#64748b",
    "queued": "#64748b",
}
ZERO_NOTE_ORDER = ["低频/年刊正常", "窗口内无新文", "批次未完成", "未纳入批次"]
ZERO_NOTE_COLOR = {
    "低频/年刊正常": "#1d4ed8",
    "窗口内无新文": "#64748b",
    "批次未完成": "#b45309",
    "未纳入批次": "#cbd5e1",
}
ZERO_NOTE_CLASS = {
    "低频/年刊正常": "zt-low",
    "窗口内无新文": "zt-none",
    "批次未完成": "zt-incomplete",
    "未纳入批次": "zt-uncovered",
}


# ---------------------------------------------------------------------------
# 基础格式化
# ---------------------------------------------------------------------------


def e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_int(value: int | float) -> str:
    return f"{int(round(value)):,}"


def pct(part: float, whole: float, digits: int = 1) -> str:
    if not whole:
        return "—"
    return f"{part / whole * 100:.{digits}f}%"


def to_int(value, default: int = 0) -> int:
    try:
        text = str(value).strip()
        return int(float(text)) if text else default
    except (TypeError, ValueError):
        return default


def to_float(value, default: float = 0.0) -> float:
    try:
        text = str(value).strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def fmt_size(path: Path) -> str:
    if not path.exists():
        return "缺失"
    size = path.stat().st_size
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{max(1, round(size / 1024))} KB"


def fmt_duration(seconds) -> str:
    if not seconds:
        return "—"
    seconds = int(round(float(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def fmt_datetime(value) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def rel_link(target: Path, base: Path) -> str:
    try:
        text = os.path.relpath(target, base)
    except ValueError:
        text = str(target)
    return text.replace("\\", "/")


def json_value(raw, default):
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def read_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# HTML 小组件
# ---------------------------------------------------------------------------


def chip(label: str, cls: str, title: str = "") -> str:
    title_attr = f' title="{e(title)}"' if title else ""
    return f'<span class="chip {cls}"{title_attr}>{e(label)}</span>'


def edition_chip(edition: str) -> str:
    key = edition if edition in EDITION_LABEL else "?"
    cls = {"SCIE": "ed-scie", "SSCI": "ed-ssci", "ESCI": "ed-esci",
           "AHCI": "ed-ahci", "?": "ed-na"}[key]
    return f'<span class="chip {cls}">{e(EDITION_LABEL[key])}</span>'


def batch_status_chip(status: str) -> str:
    key = status if status in BATCH_STATUS_LABEL else "missing"
    return chip(BATCH_STATUS_LABEL[key], BATCH_STATUS_CHIP[key], key)


def bar_row(label: str, value: float, max_value: float, value_text: str,
            sub_text: str = "", color: str = "#0f766e", scale: str = "linear") -> str:
    ratio = value / max_value if max_value else 0.0
    width = ratio * 100 if scale == "linear" else math.sqrt(max(0.0, ratio)) * 100
    if value > 0:
        width = max(width, 1.2)
    width = min(width, 100.0)
    sub_html = f"<span>{e(sub_text)}</span>" if sub_text else ""
    return (
        '<div class="bar-row">'
        f'<div class="bar-label" title="{e(label)}">{e(label)}</div>'
        '<div class="bar-track">'
        f'<span class="bar-fill" style="width:{width:.2f}%;background:{color}"></span>'
        "</div>"
        f'<div class="bar-value"><b>{e(value_text)}</b>{sub_html}</div>'
        "</div>"
    )


def stacked_bar(segments: list[tuple[str, int, str]], total: int) -> str:
    pieces = []
    for label, count, color in segments:
        if count <= 0:
            continue
        width = count / total * 100 if total else 0
        text = str(count) if width >= 7 else ""
        pieces.append(
            f'<span class="seg" style="width:{width:.3f}%;background:{color}" '
            f'title="{e(label)}：{count} 本">{text}</span>'
        )
    return '<div class="stack">' + "".join(pieces) + "</div>"


def legend(segments: list[tuple[str, int, str]], total: int) -> str:
    items = []
    for label, count, color in segments:
        items.append(
            '<span class="legend-item">'
            f'<i style="background:{color}"></i>{e(label)} '
            f'<b>{fmt_int(count)}</b><span class="muted">（{pct(count, total)}）</span>'
            "</span>"
        )
    return '<div class="legend">' + "".join(items) + "</div>"


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------


def load_package_journals(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(data, dict):
        data = data.get("journals") or []
    output = {}
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and row.get("journal_key"):
                output[str(row["journal_key"])] = row
    return output


def load_watchlist(path: Path, meta: dict[str, dict]) -> tuple[list[dict], dict]:
    rows = read_csv_rows(path)
    seen: set[str] = set()
    output: list[dict] = []
    excluded = 0
    duplicate_keys: list[str] = []
    for row in rows:
        if (row.get("include_daily") or "").strip().lower() != "yes":
            excluded += 1
            continue
        key = (row.get("journal_id") or "").strip()
        if not key:
            continue
        if key in seen:
            duplicate_keys.append(key)
            continue
        seen.add(key)
        fallback = meta.get(key, {})
        title = (row.get("title") or "").strip() or str(fallback.get("name") or key)
        issn = (row.get("issn") or "").strip()
        eissn = (row.get("eissn") or "").strip()
        edition = (row.get("edition") or "").strip() or str(fallback.get("edition") or "?").strip() or "?"
        frequency_class = (
            (row.get("frequency_class") or "").strip()
            or str(fallback.get("frequency_class") or "").strip()
            or "unknown"
        ).lower()
        publication_frequency = (
            (row.get("publication_frequency") or "").strip()
            or str(fallback.get("publication_frequency") or "").strip()
        )
        issues = to_int(row.get("issues_per_year"), 0) or to_int(fallback.get("issues_per_year"), 0)
        category = (
            (row.get("primary_category") or "").strip()
            or str(fallback.get("primary_category") or "").strip()
            or "未标注"
        )
        scopus_active = (
            (row.get("scopus_active") or "").strip()
            or str(fallback.get("scopus_active") or "").strip()
            or "Unknown"
        )
        output.append({
            "journal_key": key,
            "title": title,
            "issn": issn or str(fallback.get("issn") or "").strip(),
            "eissn": eissn,
            "edition": edition,
            "frequency_class": frequency_class,
            "publication_frequency": publication_frequency,
            "issues_per_year": issues,
            "primary_category": category,
            "scopus_active": scopus_active,
        })
    stats = {
        "total_rows": len(rows),
        "daily_rows": len(output),
        "excluded": excluded,
        "duplicate_keys": duplicate_keys,
    }
    return output, stats


def load_package_snapshots(store: PlatformStore, run_id: int) -> list[dict]:
    """只读 package_runs 的 request_snapshot_json / result_json 等字段。"""
    connection = store.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT pr.id,pr.package_id,p.package_key,pr.attempt_no,pr.execution_id,
                pr.status,pr.fetched,pr.inserted,pr.updated,pr.unchanged,pr.rejected,
                pr.request_snapshot_json,pr.result_json,pr.error_code,pr.error_message
                FROM package_runs pr JOIN crawler_packages p ON p.id=pr.package_id
                WHERE pr.run_id=%s ORDER BY pr.id""",
                (run_id,),
            )
            return list(cursor.fetchall())
    finally:
        connection.close()


def read_items_file(path: Path) -> dict:
    stats = {
        "exists": path.exists(),
        "total": 0,
        "abstracts": 0,
        "dois": 0,
        "missing_key": 0,
        "bad_lines": 0,
        "by_journal": {},
    }
    if not path.exists():
        return stats
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                stats["bad_lines"] += 1
                continue
            if not isinstance(item, dict):
                stats["bad_lines"] += 1
                continue
            stats["total"] += 1
            key = str(item.get("journal_key") or "").strip()
            if not key:
                stats["missing_key"] += 1
                continue
            row = stats["by_journal"].setdefault(
                key, {"items": 0, "abstracts": 0, "doi_items": 0}
            )
            row["items"] += 1
            abstract = str(item.get("abstract") or "").strip()
            if abstract and abstract not in {"-", "无"}:
                row["abstracts"] += 1
                stats["abstracts"] += 1
            doi = str(item.get("doi") or "").strip()
            if doi and doi not in {"-", "无"}:
                row["doi_items"] += 1
                stats["dois"] += 1
    return stats


def latest_attempts(rows: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("package_key") or "")
        current = latest.get(key)
        if current is None or to_int(row.get("attempt_no"), 0) >= to_int(current.get("attempt_no"), 0):
            latest[key] = row
    return list(latest.values())


def empty_batch(run_id: int, status: str = "missing", error: str = "") -> dict:
    return {
        "run_id": run_id,
        "monitor_id": None,
        "batch_name": f"run-{run_id}",
        "status": status,
        "started_at": None,
        "finished_at": None,
        "target_keys": set(),
        "key_complete": {},
        "per_key": {},
        "target_count": 0,
        "ok_count": 0,
        "zero_count": 0,
        "items": 0,
        "abstracts": 0,
        "doi_items": 0,
        "bad_lines": 0,
        "missing_key": 0,
        "complete": False,
        "packages": [],
        "package_statuses": [],
        "error": error,
        "warnings": [],
        "duration_seconds": None,
        "lookback_days": set(),
        "attempt_no": 0,
    }


def process_run(store: PlatformStore, run_id: int, monitor_names: dict[int, str]) -> dict:
    run = store.run(run_id)
    snapshots = latest_attempts(load_package_snapshots(store, run_id))
    batch = empty_batch(run_id, status=str(run.get("status") or "unknown"))
    batch["monitor_id"] = run.get("monitor_id")
    batch["batch_name"] = monitor_names.get(run_id) or f"run-{run_id}"
    batch["started_at"] = run.get("started_at")
    batch["finished_at"] = run.get("finished_at")
    errors = []
    if run.get("error_message"):
        errors.append(str(run["error_message"]))
    warnings: list[str] = []
    durations: list[float] = []
    complete_flags: list[bool] = []

    for row in snapshots:
        snapshot = json_value(row.get("request_snapshot_json"), {})
        params = snapshot.get("parameters") if isinstance(snapshot, dict) else {}
        params = params if isinstance(params, dict) else {}
        keys = [str(key) for key in (params.get("journal_keys") or []) if str(key).strip()]
        if params.get("lookback_days") is not None:
            batch["lookback_days"].add(to_int(params.get("lookback_days"), 0))
        batch["attempt_no"] = max(batch["attempt_no"], to_int(row.get("attempt_no"), 0))

        execution_id = str(row.get("execution_id") or "")
        output_dir = SETTINGS.runs_dir / execution_id / "output"
        items_path = output_dir / "items.jsonl"
        result = read_json_file(output_dir / "result.json")
        item_stats = read_items_file(items_path)

        result_status = str(result.get("status") or "")
        package_status = str(row.get("status") or "")
        output_ok = items_path.exists() or result_status in {"completed", "partial"}
        complete = package_status in {"completed", "partial"} and output_ok
        complete_flags.append(complete)

        batch["target_keys"].update(keys)
        batch["items"] += item_stats["total"]
        batch["abstracts"] += item_stats["abstracts"]
        batch["doi_items"] += item_stats["dois"]
        batch["bad_lines"] += item_stats["bad_lines"]
        batch["missing_key"] += item_stats["missing_key"]
        for key, counts in item_stats["by_journal"].items():
            agg = batch["per_key"].setdefault(
                key, {"items": 0, "abstracts": 0, "doi_items": 0}
            )
            agg["items"] += counts["items"]
            agg["abstracts"] += counts["abstracts"]
            agg["doi_items"] += counts["doi_items"]
        for key in set(keys) | set(item_stats["by_journal"]):
            batch["key_complete"][key] = batch["key_complete"].get(key, False) or complete

        if row.get("error_message"):
            errors.append(str(row["error_message"]))
        if result.get("error"):
            errors.append(str(result["error"]))
        for warning in result.get("warnings") or []:
            warnings.append(str(warning))
        if result.get("duration_seconds") is not None:
            durations.append(to_float(result.get("duration_seconds"), 0.0))

        batch["packages"].append({
            "package_key": str(row.get("package_key") or ""),
            "execution_id": execution_id,
            "status": package_status,
            "attempt_no": to_int(row.get("attempt_no"), 0),
            "targets": len(keys),
            "items": item_stats["total"],
            "abstracts": item_stats["abstracts"],
            "dois": item_stats["dois"],
            "complete": complete,
            "result_status": result_status,
            "error": str(row.get("error_message") or result.get("error") or ""),
        })
        batch["package_statuses"].append(package_status)

    batch["complete"] = bool(complete_flags) and all(complete_flags)
    batch["target_count"] = len(batch["target_keys"])
    if not batch["target_keys"]:
        batch["target_keys"] = set(batch["per_key"])
        batch["target_count"] = len(batch["target_keys"])
    batch["ok_count"] = sum(
        1 for key in batch["target_keys"]
        if batch["per_key"].get(key, {}).get("items", 0) > 0
    )
    batch["zero_count"] = len(batch["target_keys"]) - batch["ok_count"]
    batch["warnings"] = list(dict.fromkeys(warnings))
    batch["error"] = "; ".join(dict.fromkeys(errors))
    if durations:
        batch["duration_seconds"] = max(durations)
    elif run.get("started_at") and run.get("finished_at"):
        try:
            batch["duration_seconds"] = (
                run["finished_at"] - run["started_at"]
            ).total_seconds()
        except TypeError:
            batch["duration_seconds"] = None
    return batch


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------


def is_low_frequency(journal: dict) -> bool:
    if journal["frequency_class"] in LOW_FREQ_CLASSES:
        return True
    return 0 < journal["issues_per_year"] <= 3


def freq_label(journal: dict) -> str:
    return FREQ_LABEL.get(journal["frequency_class"], journal["frequency_class"] or "频次未知")


def freq_detail(journal: dict) -> str:
    detail = journal["publication_frequency"]
    if detail:
        return detail
    if journal["issues_per_year"]:
        return f"{journal['issues_per_year']} 期/年"
    return ""


def short_batch_name(name: str) -> str:
    return name.rsplit("-", 1)[-1] if "-" in name else name


def build_journal_records(journals: list[dict], batches: list[dict]) -> tuple[dict, Counter]:
    best: dict[str, dict] = {}
    duplicates: Counter = Counter()
    for batch in batches:
        keys = set(batch["target_keys"]) | set(batch["per_key"])
        for key in keys:
            counts = batch["per_key"].get(key, {"items": 0, "abstracts": 0, "doi_items": 0})
            complete = batch["key_complete"].get(key, batch["complete"])
            record = {
                "run_id": batch["run_id"],
                "batch_name": batch["batch_name"],
                "monitor_id": batch["monitor_id"],
                "items": to_int(counts.get("items"), 0),
                "abstracts": to_int(counts.get("abstracts"), 0),
                "doi_items": to_int(counts.get("doi_items"), 0),
                "complete": bool(complete),
                "attempt_no": batch["attempt_no"],
                "run_status": batch["status"],
            }
            record["rank"] = (
                1 if record["items"] > 0 else 0,
                1 if record["complete"] else 0,
                record["run_id"],
                record["attempt_no"],
            )
            if key in best:
                duplicates[key] += 1
            if key not in best or record["rank"] > best[key]["rank"]:
                best[key] = record
    return best, duplicates


# ---------------------------------------------------------------------------
# CSS / JS
# ---------------------------------------------------------------------------

CSS = """
:root {
  --bg: #f2f6f6;
  --panel: #ffffff;
  --ink: #102a33;
  --muted: #5d7078;
  --line: #dbe5e6;
  --soft: #f6f9f9;
  --teal: #0f5f57;
  --teal-dark: #0a3f3a;
  --amber: #b45309;
  --blue: #1d4ed8;
  --purple: #7c3aed;
  --red: #b91c1c;
  --radius: 14px;
  --shadow: 0 1px 2px rgba(16, 42, 51, .04), 0 8px 24px rgba(16, 42, 51, .05);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background:
    radial-gradient(circle at 8% 0%, rgba(15, 95, 87, .07), transparent 28rem),
    radial-gradient(circle at 92% 12%, rgba(29, 78, 216, .05), transparent 30rem),
    var(--bg);
  color: var(--ink);
  font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--teal); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { color: var(--teal-dark); }
.wrap { max-width: 1400px; margin: 0 auto; padding: 28px 24px 48px; }
.muted { color: var(--muted); }
.num, .bar-value, .kpi-value { font-variant-numeric: tabular-nums; }

.hero {
  position: relative;
  overflow: hidden;
  color: #f5fbfa;
  background: linear-gradient(125deg, #082f2c 0%, #0d4a44 48%, #123f5c 100%);
  border-radius: 20px;
  padding: 34px 36px 30px;
  box-shadow: 0 16px 40px rgba(8, 47, 44, .18);
}
.hero::after {
  content: "";
  position: absolute;
  right: -80px;
  top: -120px;
  width: 380px;
  height: 380px;
  border-radius: 50%;
  border: 44px solid rgba(255, 255, 255, .05);
  pointer-events: none;
}
.eyebrow {
  font-size: 11.5px;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: #9fd8cf;
  font-weight: 700;
}
.hero h1 {
  margin: 8px 0 10px;
  font-size: clamp(26px, 3.2vw, 40px);
  line-height: 1.22;
  letter-spacing: -.01em;
}
.hero .lede {
  max-width: 900px;
  margin: 0;
  color: #d2e8e4;
  font-size: 14.5px;
}
.hero-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }
.hero-chips span {
  border: 1px solid rgba(255, 255, 255, .18);
  background: rgba(255, 255, 255, .08);
  border-radius: 999px;
  padding: 4px 11px;
  font-size: 12px;
  color: #e5f5f2;
}
.topnav { display: flex; flex-wrap: wrap; gap: 4px; margin: 18px 0 6px; }
.topnav a {
  color: var(--muted);
  text-decoration: none;
  font-size: 12.5px;
  padding: 5px 10px;
  border-radius: 999px;
}
.topnav a:hover { background: #e6efee; color: var(--teal-dark); }

.callout {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  border: 1px solid #efd2a8;
  background: #fff8eb;
  border-radius: 12px;
  padding: 13px 16px;
  margin: 16px 0 0;
  color: #74440c;
  font-size: 13px;
}
.callout strong { color: #5c3407; }
.callout .mark {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #d97706;
  color: #fff;
  font-weight: 800;
  font-size: 13px;
  line-height: 22px;
  text-align: center;
  margin-top: 1px;
}

.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
  gap: 12px;
  margin-top: 18px;
}
.kpi {
  background: var(--panel);
  border: 1px solid var(--line);
  border-top: 3px solid var(--k, var(--teal));
  border-radius: var(--radius);
  padding: 15px 16px 13px;
  box-shadow: var(--shadow);
  min-width: 0;
}
.kpi.primary {
  color: #fff;
  background: linear-gradient(145deg, #0d4a44, #0f5f57);
  border-color: transparent;
}
.kpi.primary .kpi-label, .kpi.primary .kpi-sub { color: #c9e6e1; }
.kpi.primary .kpi-value { color: #fff; }
.kpi-label { font-size: 12px; color: var(--muted); font-weight: 600; }
.kpi-value { font-size: clamp(22px, 2.4vw, 32px); line-height: 1.15; font-weight: 750; margin-top: 5px; letter-spacing: -.01em; }
.kpi-sub { font-size: 11.5px; color: var(--muted); margin-top: 3px; }
.kpi.warn { --k: #b45309; }
.kpi.ok { --k: #0f766e; }

.section { margin-top: 34px; scroll-margin-top: 16px; }
.section-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 9px 12px; margin-bottom: 13px; }
.secnum {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  color: var(--teal);
  background: #e0efec;
  border-radius: 6px;
  padding: 2px 7px;
}
.section-head h2 { margin: 0; font-size: 21px; letter-spacing: -.01em; }
.section-head p { margin: 0; color: var(--muted); font-size: 12.5px; }
.grid-2 { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, .95fr); gap: 16px; align-items: start; }
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 20px 22px 18px;
  box-shadow: var(--shadow);
  min-width: 0;
}
.panel h3 { margin: 0 0 3px; font-size: 15.5px; }
.panel-sub { margin: 0 0 16px; color: var(--muted); font-size: 12.5px; }
.panel .divider { height: 1px; background: var(--line); margin: 18px 0 15px; }
.footnote { margin: 14px 0 0; color: var(--muted); font-size: 11.5px; line-height: 1.55; }

.bar-row {
  display: grid;
  grid-template-columns: minmax(120px, 238px) minmax(90px, 1fr) 96px;
  gap: 11px;
  align-items: center;
  margin: 9px 0;
}
.bar-label {
  font-size: 12.5px;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar-track { height: 10px; background: #edf2f3; border-radius: 999px; overflow: hidden; }
.bar-fill { display: block; height: 100%; border-radius: 999px; }
.bar-value { text-align: right; line-height: 1.3; }
.bar-value b { display: block; font-size: 12.5px; }
.bar-value span { display: block; font-size: 10.5px; color: var(--muted); }

.stack {
  display: flex;
  height: 27px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e3ebec;
  background: #f0f4f5;
}
.seg {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  min-width: 0;
}
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 9px; font-size: 11.5px; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; }
.legend-item i { width: 9px; height: 9px; border-radius: 3px; display: inline-block; }
.legend-item b { font-variant-numeric: tabular-nums; }
.stack-block + .stack-block { margin-top: 18px; }
.stack-title { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; font-weight: 650; margin-bottom: 7px; }
.stack-title span { color: var(--muted); font-weight: 400; }
.mini-list { margin: 14px 0 0; padding: 0; list-style: none; display: grid; gap: 5px; font-size: 12px; color: var(--muted); }
.mini-list b { color: var(--ink); font-variant-numeric: tabular-nums; }

.chip {
  display: inline-block;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 10.5px;
  font-weight: 700;
  line-height: 1.55;
  white-space: nowrap;
  border: 1px solid transparent;
}
.chip.mini { padding: 0 5px; font-size: 9.5px; margin-left: 3px; }
.chip-green { background: #dcf3ec; color: #0a6155; border-color: #b9e4d9; }
.chip-blue { background: #e3ebfc; color: #1e40af; border-color: #c7d6f8; }
.chip-purple { background: #ede8fb; color: #5b21b6; border-color: #dcd1f7; }
.chip-amber { background: #fdf0d8; color: #92500a; border-color: #f5ddb2; }
.chip-red { background: #fde5e5; color: #991b1b; border-color: #f6caca; }
.chip-gray { background: #eef2f4; color: #52646d; border-color: #dde6e9; }
.ed-scie { background: #e3ebfc; color: #1e40af; }
.ed-ssci { background: #dcf3ec; color: #0a6155; }
.ed-esci { background: #ede8fb; color: #5b21b6; }
.ed-ahci { background: #fdf0d8; color: #92500a; }
.ed-na { background: #eef2f4; color: #52646d; }
.zero-tag {
  display: inline-block;
  margin-top: 3px;
  border-radius: 999px;
  padding: 0 6px;
  font-size: 10px;
  line-height: 1.6;
  border: 1px solid transparent;
  white-space: nowrap;
}
.zt-low { background: #e3ebfc; color: #1e40af; border-color: #c7d6f8; }
.zt-none { background: #eef2f4; color: #52646d; border-color: #dde6e9; }
.zt-incomplete { background: #fdf0d8; color: #92500a; border-color: #f5ddb2; }
.zt-uncovered { background: #f1f5f9; color: #64748b; border-color: #e2e8f0; }

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 9px;
  margin: 0 0 12px;
}
.toolbar input[type="search"] {
  flex: 1 1 300px;
  min-width: 230px;
  border: 1px solid #cfdcde;
  border-radius: 9px;
  padding: 9px 12px;
  font: inherit;
  font-size: 12.5px;
  color: var(--ink);
  background: #fff;
  outline: none;
}
.toolbar input[type="search"]:focus { border-color: var(--teal); box-shadow: 0 0 0 3px rgba(15, 95, 87, .12); }
.toolbar select {
  border: 1px solid #cfdcde;
  border-radius: 9px;
  padding: 8px 10px;
  font: inherit;
  font-size: 12.5px;
  color: var(--ink);
  background: #fff;
  max-width: 215px;
}
.toolbar button {
  border: 1px solid #cfdcde;
  border-radius: 9px;
  padding: 8px 13px;
  font: inherit;
  font-size: 12.5px;
  color: var(--muted);
  background: #f7fafa;
  cursor: pointer;
}
.toolbar button:hover { background: #edf5f3; color: var(--teal-dark); }
.toolbar .download {
  color: var(--teal);
  text-decoration: none;
  border: 1px solid #c7dcd8;
  border-radius: 9px;
  padding: 8px 12px;
  background: #f3fafa;
  white-space: nowrap;
}
.visible-count { margin-left: auto; font-size: 12px; color: var(--muted); white-space: nowrap; }

.table-wrap {
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: auto;
  max-height: 78vh;
  background: #fff;
  box-shadow: var(--shadow);
}
table.data {
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  min-width: 1180px;
  font-size: 12px;
}
table.batch { min-width: 1120px; }
table.journals { min-width: 1260px; }
table.data th {
  position: sticky;
  top: 0;
  z-index: 2;
  text-align: left;
  background: #f3f8f7;
  color: #334b53;
  font-size: 11px;
  letter-spacing: .02em;
  padding: 10px 9px;
  border-bottom: 1px solid #cfdcdd;
  white-space: nowrap;
}
table.data td {
  padding: 8px 9px;
  border-bottom: 1px solid #edf2f3;
  vertical-align: top;
}
table.data tbody tr:hover td { background: #f7fbfa; }
table.data tbody tr:last-child td { border-bottom: 0; }
tr[hidden] { display: none !important; }
.col-idx { width: 38px; color: #93a4aa; font-size: 10.5px; text-align: right; }
.col-title { min-width: 230px; max-width: 300px; }
.jtitle { display: block; font-weight: 650; line-height: 1.4; }
.jmeta { display: block; color: #87979d; font-size: 10.5px; margin-top: 2px; }
.col-cat { min-width: 150px; max-width: 215px; font-size: 11.2px; line-height: 1.45; color: #354e56; }
.col-freq { min-width: 105px; white-space: nowrap; }
.freq-main { display: block; font-weight: 600; }
.col-num { min-width: 62px; text-align: right; white-space: nowrap; }
.num-main { display: block; font-weight: 600; line-height: 1.35; }
.num-main.zero { color: #87979d; font-weight: 500; }
.num-sub { display: block; font-size: 10.2px; color: var(--muted); line-height: 1.35; margin-top: 1px; }
.na { color: #9aa9ae; font-size: 10.8px; }
.col-status { min-width: 126px; }
.col-batch { min-width: 102px; white-space: nowrap; }
.batch-run { display: block; font-weight: 650; }
.batch-sub { display: block; color: #87979d; font-size: 10.5px; margin-top: 1px; }
.col-duration { min-width: 68px; white-space: nowrap; }
.col-error { min-width: 165px; max-width: 250px; }
.error-text { display: block; color: #8a5a2b; font-size: 10.8px; line-height: 1.4; word-break: break-word; }
.empty-cell { text-align: center !important; padding: 30px !important; color: var(--muted); }
.table-foot { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 18px; margin-top: 9px; font-size: 11.3px; color: var(--muted); }

.notes-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.note-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-left: 4px solid var(--k, var(--amber));
  border-radius: 12px;
  padding: 15px 17px;
  box-shadow: var(--shadow);
}
.note-card h3 { margin: 0 0 5px; font-size: 13.5px; }
.note-card p { margin: 0; color: var(--muted); font-size: 12.3px; line-height: 1.6; }

.footer {
  margin-top: 34px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, .6fr);
  gap: 24px;
}
.footer h3 { margin: 0 0 9px; font-size: 14px; }
.filelist { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 22px; }
.filelist li { display: flex; justify-content: space-between; gap: 10px; border-bottom: 1px dashed #e2eaeb; padding: 4px 0; font-size: 12px; }
.filelist a { text-decoration: none; }
.filelist a:hover { text-decoration: underline; }
.filelist .size { color: #94a3a8; font-size: 10.5px; white-space: nowrap; }
.footmeta { font-size: 11.5px; color: var(--muted); }
.footmeta code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10.5px; background: #eef3f4; padding: 1px 4px; border-radius: 4px; }

@media (max-width: 1040px) {
  .kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .grid-2 { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .wrap { padding: 16px 12px 32px; }
  .hero { padding: 25px 22px 23px; border-radius: 16px; }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .notes-grid { grid-template-columns: 1fr; }
  .bar-row { grid-template-columns: 112px minmax(70px, 1fr) 78px; gap: 8px; }
  .bar-label { font-size: 11.5px; }
  .footer { grid-template-columns: 1fr; }
  .filelist { grid-template-columns: 1fr; }
  .toolbar select { max-width: none; flex: 1 1 160px; }
  .visible-count { margin-left: 0; }
}
@media print {
  body { background: #fff; }
  .wrap { max-width: none; padding: 0; }
  .toolbar { display: none; }
  .table-wrap { max-height: none; overflow: visible; box-shadow: none; }
  .panel, .kpi, .note-card { box-shadow: none; break-inside: avoid; }
  .topnav { display: none; }
}
"""

JS = """
(function () {
  var rows = Array.prototype.slice.call(document.querySelectorAll('#journal-body tr.jrow'));
  var q = document.getElementById('journal-search');
  var ed = document.getElementById('filter-edition');
  var freq = document.getElementById('filter-frequency');
  var status = document.getElementById('filter-status');
  var note = document.getElementById('filter-zero-note');
  var count = document.getElementById('visible-count');
  var empty = document.getElementById('empty-row');

  function apply() {
    var term = q.value.trim().toLowerCase();
    var edition = ed.value;
    var frequency = freq.value;
    var state = status.value;
    var zeroNote = note.value;
    var visible = 0;
    rows.forEach(function (row) {
      var ok = (!term || row.getAttribute('data-search').indexOf(term) !== -1) &&
               (!edition || row.getAttribute('data-edition') === edition) &&
               (!frequency || row.getAttribute('data-frequency') === frequency) &&
               (!state || row.getAttribute('data-status') === state) &&
               (!zeroNote || row.getAttribute('data-note') === zeroNote);
      row.hidden = !ok;
      if (ok) { visible += 1; }
    });
    count.textContent = '显示 ' + visible + ' / ' + rows.length + ' 本';
    empty.hidden = visible !== 0;
  }

  q.addEventListener('input', apply);
  ed.addEventListener('change', apply);
  freq.addEventListener('change', apply);
  status.addEventListener('change', apply);
  note.addEventListener('change', apply);
  document.getElementById('reset-filters').addEventListener('click', function () {
    q.value = '';
    ed.value = '';
    freq.value = '';
    status.value = '';
    note.value = '';
    apply();
    q.focus();
  });
  apply();
})();
"""


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------


def build_html(context: dict) -> str:
    journals = context["journals"]
    batches = context["batches"]
    rows = context["rows"]
    total = context["total"]
    covered = context["covered"]
    completed_covered = context["completed_covered"]
    covered_zero = context["covered_zero"]
    uncovered = context["uncovered"]
    ok_count = context["ok_count"]
    zero_count = context["zero_count"]
    items_total = context["items_total"]
    abstracts_total = context["abstracts_total"]
    doi_total = context["doi_total"]
    zero_counts = context["zero_counts"]
    edition_counts = context["edition_counts"]
    edition_ok = context["edition_ok"]
    freq_counts = context["freq_counts"]
    freq_ok = context["freq_ok"]
    cat_counts = context["cat_counts"]
    cat_ok = context["cat_ok"]
    report_date = context["report_date"]
    generated_at = context["generated_at"]
    run_ids = context["run_ids"]
    csv_path = context["csv_path"]
    out_dir = context["out_dir"]
    prefix = context["prefix"]
    watchlist = context["watchlist"]
    package_json = context["package_json"]
    lookback_text = context["lookback_text"]
    duplicate_count = context["duplicate_count"]

    top15 = cat_counts.most_common(15)
    max_cat = top15[0][1] if top15 else 1
    completed_batches = sum(1 for batch in batches if batch["status"] == "completed")
    unfinished_batches = len(batches) - completed_batches
    incomplete_covered = max(0, covered - completed_covered)

    kpi_cards = [
        ("Q1 总刊数", fmt_int(total), "JCR 2025 Q1 · include_daily=yes", "primary", ""),
        ("采集批次", fmt_int(len(batches)),
         f"完成 {completed_batches} · 未完成/异常 {unfinished_batches}", "", "#0f766e"),
        ("文章条数", fmt_int(items_total), f"纳入批次 {fmt_int(covered)} 本", "", "#1d4ed8"),
        ("有结果刊", fmt_int(ok_count),
         f"占纳入 {pct(ok_count, covered)} · 完成覆盖 {fmt_int(completed_covered)}", "ok", "#0f766e"),
        ("0 条刊", fmt_int(zero_count),
         f"纳入内 {fmt_int(covered_zero)} · 未纳入 {fmt_int(uncovered)}", "warn", "#b45309"),
        ("含 DOI", fmt_int(doi_total), f"占文章 {pct(doi_total, items_total)}", "", "#7c3aed"),
        ("含摘要", fmt_int(abstracts_total), f"摘要率 {pct(abstracts_total, items_total)}", "", "#0f766e"),
    ]
    kpi_html = []
    for label, value, sub, variant, color in kpi_cards:
        style = f' style="--k:{color}"' if color else ""
        kpi_html.append(
            f'<div class="kpi {variant}"{style}>'
            f'<div class="kpi-label">{e(label)}</div>'
            f'<div class="kpi-value">{e(value)}</div>'
            f'<div class="kpi-sub">{e(sub)}</div>'
            "</div>"
        )

    chips = [
        f"Q1 日更候选 {fmt_int(total)} 本",
        f"批次 {len(batches)} 个",
        f"纳入 {fmt_int(covered)} 本",
        f"完成覆盖 {fmt_int(completed_covered)} 本",
        f"lookback {lookback_text}",
        f"快照 {report_date}",
        "只读 · 无 CDN",
    ]
    chips_html = "".join(f"<span>{e(item)}</span>" for item in chips)

    callout_parts = []
    if uncovered:
        callout_parts.append(
            f"本次仅纳入 {fmt_int(covered)} / {fmt_int(total)} 本（{len(batches)} 个批次），"
            f"其余 {fmt_int(uncovered)} 本未进入所选批次；这些行的 0 条标注为“未纳入批次”，"
            "不代表窗口内无新文。"
        )
    if incomplete_covered:
        callout_parts.append(
            f"已纳入的 {fmt_int(covered)} 本中，{fmt_int(incomplete_covered)} 本所在批次"
            "未完成或被取消，0 条标注为“批次未完成”。"
        )
    if covered_zero:
        callout_parts.append(
            f"完成批次内 {fmt_int(max(0, covered_zero - incomplete_covered))} 本为 0 条，"
            "按出版频次区分为“低频/年刊正常”与“窗口内无新文”。"
        )
    if not callout_parts:
        callout_parts.append(f"全量 {fmt_int(total)} 本均纳入并完成批次。")
    callout_html = (
        '<div class="callout" role="note"><span class="mark">!</span><div>'
        + "<strong>覆盖口径：</strong>" + " ".join(callout_parts)
        + "</div></div>"
    )

    # Edition 图
    edition_bars = []
    for edition in EDITION_ORDER:
        count = edition_counts.get(edition, 0)
        edition_bars.append(
            bar_row(
                EDITION_LABEL[edition], count, total, fmt_int(count),
                f"有结果 {edition_ok.get(edition, 0)}", EDITION_COLOR[edition],
            )
        )
    edition_segments = [
        (EDITION_LABEL[edition], edition_counts.get(edition, 0), EDITION_COLOR[edition])
        for edition in EDITION_ORDER
    ]

    # 频次图
    freq_bars = []
    max_freq = max((freq_counts.get(key, 0) for key in FREQ_ORDER), default=1) or 1
    for key in FREQ_ORDER:
        count = freq_counts.get(key, 0)
        if not count:
            continue
        freq_bars.append(
            bar_row(
                FREQ_LABEL.get(key, key), count, max_freq, fmt_int(count),
                f"有结果 {freq_ok.get(key, 0)}", "#0f766e",
            )
        )

    # Top 15 学科
    top15_bars = []
    for category, count in top15:
        color = "#d97706" if category == "Multiple" else "#0f766e"
        top15_bars.append(
            bar_row(
                category, count, max_cat, fmt_int(count),
                f"有结果 {cat_ok.get(category, 0)}", color, scale="sqrt",
            )
        )

    # 每批条数
    batch_bars = []
    max_batch_items = max((batch["items"] for batch in batches), default=1) or 1
    for batch in batches:
        status = batch["status"] if batch["status"] in BATCH_COLOR else "missing"
        batch_bars.append(
            bar_row(
                f'run {batch["run_id"]}', batch["items"], max_batch_items,
                fmt_int(batch["items"]),
                f'有结果 {batch["ok_count"]} · 0 条 {batch["zero_count"]}',
                BATCH_COLOR[status],
            )
        )
    if not batch_bars:
        batch_bars.append('<p class="footnote">没有可展示的批次。</p>')

    # 结果构成
    low_count = zero_counts.get("低频/年刊正常", 0)
    no_new_count = zero_counts.get("窗口内无新文", 0)
    incomplete_count = zero_counts.get("批次未完成", 0)
    not_included_count = zero_counts.get("未纳入批次", 0)
    result_segments = [
        ("有结果", ok_count, "#0f766e"),
        ("低频/年刊正常", low_count, ZERO_NOTE_COLOR["低频/年刊正常"]),
        ("窗口内无新文", no_new_count, ZERO_NOTE_COLOR["窗口内无新文"]),
        ("批次未完成", incomplete_count, ZERO_NOTE_COLOR["批次未完成"]),
        ("未纳入批次", not_included_count, ZERO_NOTE_COLOR["未纳入批次"]),
    ]

    # 批次表
    batch_rows_html = []
    for batch in batches:
        status = batch["status"] if batch["status"] in BATCH_STATUS_LABEL else "missing"
        package_statuses = ", ".join(dict.fromkeys(batch["package_statuses"])) or "—"
        error = batch["error"] or ""
        if batch["warnings"]:
            warning_text = f"{len(batch['warnings'])} 条 warning"
            error = f"{error}；{warning_text}" if error else warning_text
        if not error and batch["packages"]:
            missing = [p for p in batch["packages"] if not p["items"] and not p["complete"]]
            if missing:
                error = "无可用输出"
        error_html = (
            f'<span class="error-text" title="{e(error)}">{e(error)}</span>'
            if error else '<span class="na">—</span>'
        )
        batch_rows_html.append(
            "<tr>"
            f'<td class="col-idx">{batch["run_id"]}</td>'
            f'<td class="col-title"><span class="jtitle" title="{e(batch["batch_name"])}">'
            f'{e(short_batch_name(batch["batch_name"]))}</span>'
            f'<span class="jmeta" title="{e(batch["batch_name"])}">'
            f'{e(fmt_datetime(batch["started_at"]))}</span></td>'
            f'<td>{batch["monitor_id"] if batch["monitor_id"] is not None else "—"}</td>'
            f'<td>{batch_status_chip(status)}'
            f'<span class="jmeta">package: {e(package_statuses)}</span></td>'
            f'<td class="col-num">{fmt_int(batch["target_count"])}</td>'
            f'<td class="col-num"><span class="num-main">{fmt_int(batch["items"])}</span></td>'
            f'<td class="col-num">{fmt_int(batch["ok_count"])}</td>'
            f'<td class="col-num">{fmt_int(batch["zero_count"])}</td>'
            f'<td class="col-num">{fmt_int(batch["abstracts"])}</td>'
            f'<td class="col-num">{fmt_int(batch["doi_items"])}</td>'
            f'<td class="col-duration">{e(fmt_duration(batch["duration_seconds"]))}</td>'
            f'<td class="col-error">{error_html}</td>'
            "</tr>"
        )

    # 过滤器选项
    edition_options = []
    for edition in EDITION_ORDER:
        count = edition_counts.get(edition, 0)
        if count:
            edition_options.append(
                f'<option value="{e(edition)}">{e(EDITION_LABEL[edition])}（{count}）</option>'
            )
    freq_options = []
    for key in FREQ_ORDER:
        count = freq_counts.get(key, 0)
        if count:
            freq_options.append(
                f'<option value="{e(key)}">{e(FREQ_LABEL.get(key, key))}（{count}）</option>'
            )
    note_options = []
    for note in ZERO_NOTE_ORDER:
        count = zero_counts.get(note, 0)
        if count:
            note_options.append(f'<option value="{e(note)}">{e(note)}（{count}）</option>')

    # 逐刊表
    table_rows = []
    for index, journal, row in rows:
        rec = row["record"]
        items = row["items"]
        abstracts = row["abstracts"]
        doi_items = row["doi_items"]
        rate = row["abstract_rate"]
        status = row["status"]
        zero_note = row["zero_note"]
        edition = journal["edition"]
        frequency = journal["frequency_class"]
        search_blob = row["search"]
        issn_text = " · ".join(
            part for part in [
                f"ISSN {journal['issn']}" if journal["issn"] else "",
                f"eISSN {journal['eissn']}" if journal["eissn"] else "",
            ] if part
        ) or "ISSN —"
        if status == "ok":
            status_html = '<span class="chip chip-green">有结果</span>'
        else:
            note_class = ZERO_NOTE_CLASS.get(zero_note, "zt-none")
            status_html = (
                '<span class="chip chip-gray">0 条</span>'
                f'<span class="zero-tag {note_class}">{e(zero_note)}</span>'
            )
        if rec:
            batch_html = (
                f'<span class="batch-run">run {rec["run_id"]}</span>'
                f'<span class="batch-sub" title="{e(rec["batch_name"])}">'
                f'{e(short_batch_name(rec["batch_name"]))}</span>'
            )
        else:
            batch_html = '<span class="na">—</span>'
        detail = freq_detail(journal)
        detail_html = f'<span class="num-sub">{e(detail)}</span>' if detail else ""
        table_rows.append(
            f'<tr class="jrow" data-edition="{e(edition)}" data-frequency="{e(frequency)}" '
            f'data-status="{e(status)}" data-note="{e(zero_note)}" data-search="{e(search_blob)}">'
            f'<td class="col-idx">{index}</td>'
            '<td class="col-title">'
            f'<span class="jtitle" title="{e(journal["title"])}">{e(journal["title"])}</span>'
            f'<span class="jmeta">{e(issn_text)} · {e(journal["journal_key"])}</span>'
            "</td>"
            f'<td>{edition_chip(edition)}</td>'
            f'<td class="col-freq"><span class="freq-main">{e(freq_label(journal))}</span>{detail_html}</td>'
            f'<td class="col-cat" title="{e(journal["primary_category"])}">'
            f'{e(journal["primary_category"])}</td>'
            f'<td class="col-num"><span class="num-main{" zero" if items == 0 else ""}">'
            f'{fmt_int(items)}</span></td>'
            f'<td class="col-num"><span class="num-main{" zero" if abstracts == 0 else ""}">'
            f'{fmt_int(abstracts)}</span><span class="num-sub">{rate:.1f}%</span></td>'
            f'<td class="col-num"><span class="num-main{" zero" if doi_items == 0 else ""}">'
            f'{fmt_int(doi_items)}</span></td>'
            f'<td class="col-status">{status_html}</td>'
            f'<td class="col-batch">{batch_html}</td>'
            "</tr>"
        )

    # 文件链接
    file_links = [(csv_path, f"逐刊汇总 CSV（{fmt_int(total)} 行）")]
    items_csv = out_dir / f"{prefix}_items.csv"
    if items_csv.exists():
        file_links.append((items_csv, "文章明细 CSV"))
    if watchlist.exists():
        file_links.append((watchlist, "Q1 watchlist 源（5,279 行）"))
    if package_json.exists():
        file_links.append((package_json, "包 journals.json（5,238 本）"))
    link_items = []
    for path, label in file_links:
        link_items.append(
            "<li>"
            f'<a href="{e(rel_link(path, out_dir))}">{e(label)}</a>'
            f'<span class="size">{e(fmt_size(path))}</span>'
            "</li>"
        )

    runs_text = ", ".join(str(run_id) for run_id in run_ids)
    zero_summary = " · ".join(
        f"{note} {fmt_int(zero_counts.get(note, 0))}" for note in ZERO_NOTE_ORDER
    )
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>国外 Q1 全量逐刊采集报告 · {e(report_date)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

  <header class="hero">
    <div class="eyebrow">FOREIGN JOURNALS · JCR 2025 · Q1 · BULK CRAWL</div>
    <h1>国外 Q1 全量逐刊采集报告</h1>
    <p class="lede">
      汇总 {fmt_int(total)} 本 JCR 2025 全学科 Q1 日更候选刊的逐刊采集结果：
      {len(batches)} 个 bulk 批次、{fmt_int(items_total)} 篇文章、
      {fmt_int(ok_count)} 本有结果。按 journal_key 去重后每刊只出现一次，
      0 条按“低频/年刊正常 / 窗口内无新文 / 批次未完成 / 未纳入批次”区分。
    </p>
    <div class="hero-chips">{chips_html}</div>
  </header>

  <nav class="topnav" aria-label="页面导航">
    <a href="#overview">概览</a>
    <a href="#structure">全量结构</a>
    <a href="#batches">批次产出</a>
    <a href="#journals">逐刊明细</a>
    <a href="#notes">口径与限制</a>
  </nav>

  {callout_html}

  <section id="overview" class="section" aria-label="关键数字">
    <div class="kpis">{"".join(kpi_html)}</div>
  </section>

  <section id="structure" class="section">
    <div class="section-head">
      <span class="secnum">01</span>
      <h2>全量结构</h2>
      <p>{fmt_int(total)} 本日更候选刊的 Edition、出版频次与 JCR 主学科</p>
    </div>
    <div class="grid-2">
      <article class="panel">
        <h3>Edition 分布</h3>
        <p class="panel-sub">SCIE 占 {pct(edition_counts.get("SCIE", 0), total)}；
          副标题为本次有结果的刊数。</p>
        {"".join(edition_bars)}
        <div class="divider"></div>
        {stacked_bar(edition_segments, total)}
        {legend(edition_segments, total)}
        <p class="footnote">Edition 来自 watchlist；“未标注”为 edition 为 “?” 的期刊。
          Inactive 期刊仍在 Q1 全量中，但 include_daily=no，不计入本表。</p>
      </article>

      <article class="panel">
        <h3>出版频次分布</h3>
        <p class="panel-sub">按 frequency_class 统计；低频零条优先判为“低频/年刊正常”。</p>
        {"".join(freq_bars)}
        <p class="footnote">频次来自 watchlist / journals.json；年刊、半年刊、三季刊以及
          issues_per_year ≤ 3 的期刊视为低频。</p>
      </article>
    </div>

    <article class="panel" style="margin-top:16px">
      <h3>Top 15 JCR 主学科</h3>
      <p class="panel-sub">按 primary_category 统计；“Multiple”为多学科标记，副标题为有结果刊数。</p>
      {"".join(top15_bars)}
      <p class="footnote">条形长度为平方根刻度（便于展示长尾），标注为实际刊数。</p>
    </article>
  </section>

  <section id="batches" class="section">
    <div class="section-head">
      <span class="secnum">02</span>
      <h2>批次产出</h2>
      <p>所选 run 的文章条数、有结果刊、0 条刊与完成状态</p>
    </div>
    <div class="grid-2">
      <article class="panel">
        <h3>每批文章条数</h3>
        <p class="panel-sub">条数来自各 execution 的 output/items.jsonl。</p>
        {"".join(batch_bars)}
        <p class="footnote">批次顺序与 --runs 参数一致；条形颜色对应批次状态
          （绿=完成，橙=部分完成，红=失败，蓝=运行中）。</p>
      </article>
      <article class="panel">
        <h3>{fmt_int(total)} 本结果构成</h3>
        <p class="panel-sub">有结果、低频/年刊正常、窗口内无新文、批次未完成、未纳入批次。</p>
        {stacked_bar(result_segments, total)}
        {legend(result_segments, total)}
        <ul class="mini-list">
          <li>纳入批次 <b>{fmt_int(covered)}</b> 本；完成覆盖 <b>{fmt_int(completed_covered)}</b> 本；
            批次未完成 <b>{fmt_int(incomplete_covered)}</b> 本；未纳入 <b>{fmt_int(uncovered)}</b> 本。</li>
          <li>0 条合计 <b>{fmt_int(zero_count)}</b> 本：{e(zero_summary)}。</li>
          <li>多 run 合并按 journal_key 去重；重复键 <b>{fmt_int(duplicate_count)}</b> 个。</li>
        </ul>
      </article>
    </div>

    <div class="table-wrap" style="margin-top:16px">
      <table class="data batch">
        <caption style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">批次状态表</caption>
        <thead>
          <tr>
            <th scope="col">run</th>
            <th scope="col">批次</th>
            <th scope="col">monitor</th>
            <th scope="col">状态</th>
            <th scope="col">目标刊</th>
            <th scope="col">文章</th>
            <th scope="col">有结果</th>
            <th scope="col">0 条</th>
            <th scope="col">摘要</th>
            <th scope="col">DOI</th>
            <th scope="col">用时</th>
            <th scope="col">错误 / 备注</th>
          </tr>
        </thead>
        <tbody>
          {"".join(batch_rows_html)}
        </tbody>
      </table>
    </div>
    <div class="table-foot">
      <span>状态来自 monitor_runs / package_runs；目标刊数来自 request_snapshot_json 的 journal_keys；
        条数来自 output/items.jsonl。</span>
      <span>失败或取消批次的 0 条在逐刊表标注为“批次未完成”。</span>
    </div>
  </section>

  <section id="journals" class="section">
    <div class="section-head">
      <span class="secnum">03</span>
      <h2>逐刊明细</h2>
      <p>{fmt_int(total)} 本；可搜索，按 Edition / 频次 / 状态 / 零条原因筛选</p>
    </div>

    <div class="toolbar">
      <input id="journal-search" type="search"
        placeholder="搜索刊名 / ISSN / 学科 / 批次 / 零条原因…" aria-label="搜索逐刊明细">
      <select id="filter-edition" aria-label="按 Edition 筛选">
        <option value="">全部 Edition（{total}）</option>
        {"".join(edition_options)}
      </select>
      <select id="filter-frequency" aria-label="按出版频次筛选">
        <option value="">全部频次（{total}）</option>
        {"".join(freq_options)}
      </select>
      <select id="filter-status" aria-label="按状态筛选">
        <option value="">全部状态（{total}）</option>
        <option value="ok">有结果（{ok_count}）</option>
        <option value="zero">0 条（{zero_count}）</option>
      </select>
      <select id="filter-zero-note" aria-label="按零条原因筛选">
        <option value="">全部零条原因（{zero_count}）</option>
        {"".join(note_options)}
      </select>
      <button id="reset-filters" type="button">重置</button>
      <a class="download" href="{e(csv_path.name)}">下载 CSV</a>
      <span class="visible-count" id="visible-count">显示 {total} / {total} 本</span>
    </div>

    <div class="table-wrap">
      <table class="data journals">
        <caption style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">{fmt_int(total)} 本逐刊采集明细</caption>
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">期刊</th>
            <th scope="col">Edition</th>
            <th scope="col">频次</th>
            <th scope="col">主学科</th>
            <th scope="col">条数</th>
            <th scope="col">摘要</th>
            <th scope="col">DOI</th>
            <th scope="col">状态</th>
            <th scope="col">批次</th>
          </tr>
        </thead>
        <tbody id="journal-body">
          {"".join(table_rows)}
          <tr id="empty-row" hidden><td class="empty-cell" colspan="10">没有匹配的期刊，请调整关键词或筛选条件。</td></tr>
        </tbody>
      </table>
    </div>
    <div class="table-foot">
      <span>共 {fmt_int(total)} 行；保持 watchlist 行顺序。摘要率 = 摘要条数 / 条数；DOI 为 doi 非空条数。</span>
      <span>同一 journal_key 若出现在多个 run，只保留一条记录（优先有结果、已完成、较新的 run）。</span>
    </div>
    <noscript><p class="footnote">浏览器未启用 JavaScript：表格仍完整可读，但关键词与下拉筛选不可用。</p></noscript>
  </section>

  <section id="notes" class="section">
    <div class="section-head">
      <span class="secnum">04</span>
      <h2>口径与限制</h2>
      <p>阅读本报告数字前需要知道的边界</p>
    </div>
    <div class="notes-grid">
      <article class="note-card" style="--k:#b45309">
        <h3>0 条不都等于“窗口内无新文”</h3>
        <p>0 条分四类：低频/年刊正常（年刊、半年刊、三季刊或 ≤3 期/年）、
          窗口内无新文、批次未完成（run 失败/取消/无输出）、未纳入批次（该刊不在所选 run 的
          journal_keys 中）。预览或部分批次时，未纳入批次会占多数，不能据此判断期刊无更新。</p>
      </article>
      <article class="note-card" style="--k:#1d4ed8">
        <h3>频次判断是保守规则</h3>
        <p>frequency_class 为 annual / semiannual / triannual，或 issues_per_year ≤ 3 时，
          0 条标注“低频/年刊正常”；其余标注“窗口内无新文”。频次未知的刊物按“窗口内无新文”处理，
          避免把未知频次误判为年刊。</p>
      </article>
      <article class="note-card" style="--k:#0f766e">
        <h3>多 run 去重</h3>
        <p>合并多个 run 时按 journal_key 去重，同一刊只出现一次。若同一刊出现在多个 run，
          优先保留有结果的记录，其次保留已完成批次，最后保留 run_id 较大的记录；
          不把多个 run 的条数相加，避免重跑导致重复计数。</p>
      </article>
      <article class="note-card" style="--k:#7c3aed">
        <h3>指标口径</h3>
        <p>items 为 items.jsonl 中该 journal_key 的行数；abstracts 为 abstract 非空的行数；
          doi_items 为 doi 非空的行数；abstract_rate = abstracts / items。
          条数受 per_journal_limit（本批参数）与 bulk_window lookback 限制，是窗口内下界。</p>
      </article>
      <article class="note-card" style="--k:#64748b">
        <h3>只读、可复现</h3>
        <p>脚本用 PlatformStore(SETTINGS).run(run_id) 读取运行与 package_runs 状态，
          再读取 crawler_platform_runtime/runs/&lt;execution_id&gt;/output/ 下的 items.jsonl 与 result.json；
          不联网、不写数据库、不创建任务，也不修改平台、包或 watchlist。</p>
      </article>
      <article class="note-card" style="--k:#0f766e">
        <h3>本次参数</h3>
        <p>runs：{e(runs_text)}；批次状态：完成 {completed_batches} / 共 {len(batches)}；
          lookback：{e(lookback_text)}；数据日期：{e(report_date)}；
          生成时间：{e(generated_at)}。文章明细 CSV 若存在（&lt;prefix&gt;_items.csv），页脚会自动链接。</p>
      </article>
    </div>
  </section>

  <footer class="footer">
    <div>
      <h3>数据与产物</h3>
      <ul class="filelist">{"".join(link_items)}</ul>
    </div>
    <div class="footmeta">
      <h3>说明</h3>
      <p>数据日期：{e(report_date)}<br>
      批次：{e(runs_text)}<br>
      全量：{fmt_int(total)} 本；纳入：{fmt_int(covered)} 本<br>
      生成脚本：<code>scripts/build_foreign_q1_full_report.py</code></p>
      <p>本报告只读本地运行产物与平台数据库；未联网、未写数据库。</p>
    </div>
  </footer>

</div>
<script>{JS}</script>
</body>
</html>
"""
    return html_doc


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def parse_runs(values: list[str]) -> list[int]:
    run_ids: list[int] = []
    for value in values:
        for part in str(value).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                run_id = int(part)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"run id 必须是整数: {part}") from exc
            if run_id <= 0:
                raise argparse.ArgumentTypeError(f"run id 必须为正整数: {run_id}")
            if run_id not in run_ids:
                run_ids.append(run_id)
    if not run_ids:
        raise argparse.ArgumentTypeError("--runs 至少需要一个 run id")
    return run_ids


def parse_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期必须是 YYYY-MM-DD") from exc
    return value


def parse_prefix(value: str) -> str:
    text = str(value).strip()
    if not text:
        raise argparse.ArgumentTypeError("--prefix 不能为空")
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise argparse.ArgumentTypeError("--prefix 只能是文件名前缀，不能包含路径分隔符")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成国外 Q1 全量逐刊 CSV 与可搜索 HTML 图表报告（只读）。"
    )
    parser.add_argument(
        "--runs", action="append", required=True,
        help="run id，可逗号分隔或重复传入，例如 --runs 29,30 --runs 31",
    )
    parser.add_argument("--date", type=parse_date, default=DEFAULT_DATE, help="报告数据日期 YYYY-MM-DD")
    parser.add_argument(
        "--out-dir", default="journal_catalog/foreign",
        help="输出目录（相对项目根目录或绝对路径），默认 journal_catalog/foreign",
    )
    parser.add_argument(
        "--prefix", type=parse_prefix, default=None,
        help="输出文件名前缀，默认 foreign_q1_full_<date>",
    )
    parser.add_argument(
        "--only-included", action="store_true",
        help="只输出所选 run 的目标期刊（含 0 条），默认输出完整 5,238 本并标未纳入批次",
    )
    args = parser.parse_args()

    try:
        run_ids = parse_runs(args.runs)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    report_date = args.date
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir = out_dir.resolve()
    prefix = args.prefix or f"foreign_q1_full_{report_date}"
    csv_path = out_dir / f"{prefix}_journals.csv"
    html_path = out_dir / f"{prefix}_report.html"

    for target in (csv_path, html_path):
        if target.resolve() in PROTECTED_OUTPUTS:
            raise SystemExit(f"拒绝覆盖受保护的已有文件: {target}")

    meta = load_package_journals(PACKAGE_JOURNALS_JSON)
    journals, watch_stats = load_watchlist(WATCHLIST_CSV, meta)
    total = len(journals)
    print(f"watchlist: total={watch_stats['total_rows']:,} daily={total:,} "
          f"excluded={watch_stats['excluded']:,} duplicates={len(watch_stats['duplicate_keys'])}")
    if total != EXPECTED_DAILY:
        print(f"WARNING: 日更候选 {total} != 预期 {EXPECTED_DAILY}")

    store = PlatformStore(SETTINGS)
    monitor_names = {
        int(row["id"]): str(row.get("monitor_name") or "")
        for row in store.list_runs(limit=200)
    }

    batches: list[dict] = []
    for run_id in run_ids:
        try:
            batch = process_run(store, run_id, monitor_names)
        except Exception as exc:  # noqa: BLE001 - 单个 run 缺失不应中断整份报告
            print(f"WARNING: run {run_id} 读取失败: {exc}")
            batch = empty_batch(run_id, status="missing", error=str(exc))
        batches.append(batch)
        print(
            f"run {run_id}: status={batch['status']} batch={batch['batch_name']} "
            f"target={batch['target_count']:,} items={batch['items']:,} "
            f"ok={batch['ok_count']:,} zero={batch['zero_count']:,} "
            f"abstracts={batch['abstracts']:,} doi={batch['doi_items']:,}"
        )
        if batch["packages"]:
            for package in batch["packages"]:
                if package["items"] == 0 and not package["complete"]:
                    print(f"  WARNING: run {run_id} package {package['package_key']} "
                          f"未完成（{package['status']}），无可用输出")
        if batch["bad_lines"]:
            print(f"  WARNING: run {run_id} items.jsonl 有 {batch['bad_lines']} 行无法解析")
        if batch["missing_key"]:
            print(f"  WARNING: run {run_id} 有 {batch['missing_key']} 条缺少 journal_key")

    best, duplicates = build_journal_records(journals, batches)
    if args.only_included:
        target_keys = set().union(*(batch["target_keys"] for batch in batches)) if batches else set()
        journals = [journal for journal in journals if journal["journal_key"] in target_keys]
        total = len(journals)
        print(f"only-included: {total:,} 本（所选 run 的目标刊）")
    journal_keys = {journal["journal_key"] for journal in journals}

    rows: list[dict] = []
    edition_counts = Counter()
    edition_ok = Counter()
    freq_counts = Counter()
    freq_ok = Counter()
    cat_counts = Counter()
    cat_ok = Counter()
    zero_counts = Counter()
    items_total = 0
    abstracts_total = 0
    doi_total = 0
    ok_count = 0
    covered = 0
    completed_covered = 0
    covered_zero = 0
    seen_records: set[str] = set()

    for index, journal in enumerate(journals, start=1):
        key = journal["journal_key"]
        rec = best.get(key)
        items = rec["items"] if rec else 0
        abstracts = rec["abstracts"] if rec else 0
        doi_items = rec["doi_items"] if rec else 0
        if rec:
            covered += 1
            seen_records.add(key)
            if rec["complete"]:
                completed_covered += 1
        status = "ok" if items > 0 else "zero"
        if status == "ok":
            zero_note = ""
        elif rec is None:
            zero_note = "未纳入批次"
        elif not rec["complete"]:
            zero_note = "批次未完成"
        elif is_low_frequency(journal):
            zero_note = "低频/年刊正常"
        else:
            zero_note = "窗口内无新文"
        if status == "ok":
            ok_count += 1
        else:
            covered_zero += 1 if rec else 0
            zero_counts[zero_note] += 1
        items_total += items
        abstracts_total += abstracts
        doi_total += doi_items
        rate = round(abstracts / items * 100, 1) if items else 0.0

        edition_counts[journal["edition"]] += 1
        if items > 0:
            edition_ok[journal["edition"]] += 1
        freq_counts[journal["frequency_class"]] += 1
        if items > 0:
            freq_ok[journal["frequency_class"]] += 1
        cat_counts[journal["primary_category"]] += 1
        if items > 0:
            cat_ok[journal["primary_category"]] += 1

        search_blob = " ".join([
            journal["title"],
            journal["journal_key"],
            journal["issn"],
            journal["eissn"],
            journal["edition"],
            EDITION_LABEL.get(journal["edition"], ""),
            journal["frequency_class"],
            FREQ_LABEL.get(journal["frequency_class"], ""),
            journal["publication_frequency"],
            journal["primary_category"],
            journal["scopus_active"],
            str(rec["run_id"]) if rec else "",
            f"run {rec['run_id']}" if rec else "",
            rec["batch_name"] if rec else "",
            zero_note,
        ]).lower()

        rows.append({
            "journal": journal,
            "record": rec,
            "items": items,
            "abstracts": abstracts,
            "doi_items": doi_items,
            "abstract_rate": rate,
            "status": status,
            "zero_note": zero_note,
            "search": search_blob,
        })

    duplicate_count = sum(1 for key in duplicates if key in journal_keys)
    unknown_item_keys = (set(best) - journal_keys)
    if unknown_item_keys:
        print(f"WARNING: {len(unknown_item_keys)} 个 journal_key 不在 watchlist，已忽略逐刊行")
    if duplicate_count:
        print(f"NOTE: {duplicate_count} 个 journal_key 出现在多个 run，已去重")

    zero_count = total - ok_count
    uncovered = total - covered
    if zero_counts.get("未纳入批次", 0) != uncovered:
        print(f"WARNING: 未纳入批次计数 {zero_counts.get('未纳入批次', 0)} != uncovered {uncovered}")
    if sum(zero_counts.values()) != zero_count:
        print(f"WARNING: 零条原因合计 {sum(zero_counts.values())} != zero {zero_count}")

    out_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "journal_key", "title", "issn", "edition", "frequency_class",
        "publication_frequency", "primary_category", "scopus_active",
        "items", "abstracts", "doi_items", "abstract_rate",
        "run_id", "batch_name", "status", "zero_note",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            journal = row["journal"]
            rec = row["record"]
            writer.writerow({
                "journal_key": journal["journal_key"],
                "title": journal["title"],
                "issn": journal["issn"] or journal["eissn"],
                "edition": journal["edition"],
                "frequency_class": journal["frequency_class"],
                "publication_frequency": journal["publication_frequency"],
                "primary_category": journal["primary_category"],
                "scopus_active": journal["scopus_active"],
                "items": row["items"],
                "abstracts": row["abstracts"],
                "doi_items": row["doi_items"],
                "abstract_rate": f"{row['abstract_rate']:.1f}",
                "run_id": rec["run_id"] if rec else "",
                "batch_name": rec["batch_name"] if rec else "",
                "status": row["status"],
                "zero_note": row["zero_note"],
            })

    lookbacks = sorted({value for batch in batches for value in batch["lookback_days"] if value})
    lookback_text = (
        " / ".join(f"{value} 天" for value in lookbacks) if lookbacks else "未知"
    )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_doc = build_html({
        "journals": journals,
        "batches": batches,
        "rows": [(index, row["journal"], row)
                 for index, row in enumerate(rows, start=1)],
        "total": total,
        "covered": covered,
        "completed_covered": completed_covered,
        "covered_zero": covered_zero,
        "uncovered": uncovered,
        "ok_count": ok_count,
        "zero_count": zero_count,
        "items_total": items_total,
        "abstracts_total": abstracts_total,
        "doi_total": doi_total,
        "zero_counts": zero_counts,
        "edition_counts": edition_counts,
        "edition_ok": edition_ok,
        "freq_counts": freq_counts,
        "freq_ok": freq_ok,
        "cat_counts": cat_counts,
        "cat_ok": cat_ok,
        "report_date": report_date,
        "generated_at": generated_at,
        "run_ids": run_ids,
        "csv_path": csv_path,
        "out_dir": out_dir,
        "prefix": prefix,
        "watchlist": WATCHLIST_CSV,
        "package_json": PACKAGE_JOURNALS_JSON,
        "lookback_text": lookback_text,
        "duplicate_count": duplicate_count,
    })
    html_path.write_text(html_doc, encoding="utf-8", newline="\n")

    print(f"Wrote {csv_path} ({len(rows):,} rows, {fmt_size(csv_path)})")
    print(f"Wrote {html_path} ({fmt_size(html_path)})")
    print(
        f"TOTAL journals={total:,} covered={covered:,} completed_covered={completed_covered:,} "
        f"items={items_total:,} abstracts={abstracts_total:,} "
        f"({pct(abstracts_total, items_total)}) doi={doi_total:,} "
        f"({pct(doi_total, items_total)}) ok={ok_count:,} zero={zero_count:,} "
        f"(covered zero={covered_zero:,}, uncovered={uncovered:,})"
    )
    print("zero notes: " + ", ".join(
        f"{note}={zero_counts.get(note, 0):,}" for note in ZERO_NOTE_ORDER
    ))


if __name__ == "__main__":
    main()
