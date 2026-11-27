"""create_foreign_q1_batches.py 的纯逻辑 / dry-run 测试（不连接数据库）。"""

from __future__ import annotations

import csv
import importlib.util
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "create_foreign_q1_batches.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("create_foreign_q1_batches", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def write_watchlist(path: Path, rows: list[dict[str, str]]) -> Path:
    fields = ["journal_id", "title", "include_daily"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def make_rows(count: int) -> list[dict[str, str]]:
    return [
        {"journal_id": f"id{index:016d}", "title": f"Journal {index}", "include_daily": "yes"}
        for index in range(count)
    ]


def test_load_watchlist_filters_and_dedupes(tmp_path: Path):
    path = write_watchlist(tmp_path / "w.csv", [
        {"journal_id": "a", "title": "A", "include_daily": "yes"},
        {"journal_id": "b", "title": "B", "include_daily": "no"},
        {"journal_id": "c", "title": "C", "include_daily": "yes"},
        {"journal_id": "a", "title": "A2", "include_daily": "yes"},
        {"journal_id": "", "title": "D", "include_daily": "yes"},
    ])
    rows, stats = MODULE.load_watchlist(path, "journal_id")
    assert [row["key"] for row in rows] == ["a", "c"]
    assert stats["total"] == 5
    assert stats["excluded"] == 1
    assert stats["included"] == 2
    assert stats["duplicate_keys"] == ["a"]
    assert stats["invalid"] == ["D"]


def test_build_plan_5238_by_50():
    rows = [{"key": f"id{index:016d}", "name": f"Journal {index}"} for index in range(5238)]
    plan = MODULE.build_plan(rows, 50, "2026-11-25", "国外Q1")
    assert len(plan) == 105
    assert plan[0]["name"] == "国外Q1-2026-11-25-001of105"
    assert plan[-1]["name"] == "国外Q1-2026-11-25-105of105"
    assert [batch["count"] for batch in plan[:2]] == [50, 50]
    assert plan[-1]["count"] == 38
    assert plan[0]["item_limit"] == 1000
    assert plan[-1]["item_limit"] == 760
    assert plan[0]["config"] == {
        "journal_keys": [f"id{index:016d}" for index in range(50)],
        "collect_mode": "latest_issue",
        "lookback_days": 30,
        "per_journal_limit": 20,
        "timeout_seconds": 25,
        "require_abstract": False,
    }
    assert sum(batch["count"] for batch in plan) == 5238
    keys = [key for batch in plan for key in batch["config"]["journal_keys"]]
    assert keys == [f"id{index:016d}" for index in range(5238)]


def test_naming_padding_follows_batch_count():
    rows = [{"key": f"k{index}", "name": f"Journal {index}"} for index in range(7)]
    plan = MODULE.build_plan(rows, 3, "2026-11-25", "国外Q1")
    assert [batch["name"] for batch in plan] == [
        "国外Q1-2026-11-25-1of3",
        "国外Q1-2026-11-25-2of3",
        "国外Q1-2026-11-25-3of3",
    ]


def test_per_batch_bounds():
    assert MODULE.parse_per_batch("100") == 100
    assert MODULE.parse_per_batch("1") == 1
    for bad in ("0", "101", "abc"):
        with pytest.raises(Exception):
            MODULE.parse_per_batch(bad)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT, env=env,
    )


def test_dry_run_writes_plan_and_skips_database(tmp_path: Path):
    watchlist = write_watchlist(tmp_path / "q1.csv", make_rows(5238))
    plan_out = tmp_path / "plan.csv"
    result = run_cli("--dry-run", "--watchlist", str(watchlist), "--plan-out", str(plan_out))
    assert result.returncode == 0, result.stderr
    assert "未连接数据库" in result.stdout
    with plan_out.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 105
    assert rows[0]["batch_name"] == f"国外Q1-{date.today().isoformat()}-001of105"
    assert rows[0]["package_key"] == "foreign_q1_journals"
    assert rows[0]["journals"] == "50"
    assert rows[0]["item_limit"] == "1000"
    assert all(row["monitor_id"] == "" for row in rows)
    assert rows[0]["first_journal"] == "Journal 0"
    assert rows[-1]["last_journal"] == "Journal 5237"


def test_empty_watchlist_returns_error(tmp_path: Path):
    watchlist = write_watchlist(tmp_path / "empty.csv",
                               [{"journal_id": "a", "title": "A", "include_daily": "no"}])
    plan_out = tmp_path / "plan.csv"
    result = run_cli("--dry-run", "--watchlist", str(watchlist), "--plan-out", str(plan_out))
    assert result.returncode == 3
    assert not plan_out.exists()
