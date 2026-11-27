from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import Settings
from crawler_platform.executor import Worker
from crawler_platform.storage import PlatformStore


TERMINAL = {"completed", "partial", "failed", "timed_out", "cancelled"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, action="append", required=True)
    parser.add_argument("--package-timeout", type=int, default=1200)
    parser.add_argument("--archive-monitors", action="store_true")
    parser.add_argument("--result", default="")
    args = parser.parse_args()
    settings = Settings(package_timeout_seconds=args.package_timeout, worker_poll_seconds=2)
    store = PlatformStore(settings)
    worker = Worker(settings, store)
    run_ids = list(dict.fromkeys(args.run_id))
    last: dict[tuple[int, str], tuple] = {}
    while True:
        summaries = {run_id: store.run(run_id) for run_id in run_ids}
        for run_id, run in summaries.items():
            for package in run["packages"]:
                marker = (package["status"], package["fetched"], package["rejected"])
                key = (run_id, package["package_key"])
                if marker != last.get(key):
                    print("PROGRESS", run_id, package["package_key"], marker, flush=True)
                    last[key] = marker
        pending = [run for run in summaries.values()
                   if run["status"] in {"queued", "running"} or any(p["status"] not in TERMINAL for p in run["packages"])]
        if not pending:
            break
        if not worker.run_once():
            time.sleep(2)
    summary = {}
    for run_id in run_ids:
        run = store.run(run_id)
        summary[str(run_id)] = {
            "status": run["status"], "monitor_id": run["monitor_id"],
            "fetched": run["fetched"], "inserted": run["inserted"], "updated": run["updated"],
            "unchanged": run["unchanged"], "rejected": run["rejected"],
            "packages": [{key: package.get(key) for key in (
                "package_key", "status", "fetched", "inserted", "updated", "unchanged",
                "rejected", "error_code", "error_message", "execution_id")} for package in run["packages"]],
        }
    result_path = Path(args.result) if args.result else ROOT / ".local" / "platform-runs-result.json"
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.archive_monitors:
        for run_id in run_ids:
            store.archive_monitor(store.run(run_id)["monitor_id"])
    print("FINAL", json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
