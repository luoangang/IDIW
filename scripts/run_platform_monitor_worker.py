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
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--package-timeout", type=int, default=1200)
    parser.add_argument("--archive-monitor", action="store_true")
    parser.add_argument("--result", default="")
    args = parser.parse_args()
    settings = Settings(package_timeout_seconds=args.package_timeout, worker_poll_seconds=2)
    store = PlatformStore(settings)
    worker = Worker(settings, store)
    last: dict[str, tuple] = {}
    while True:
        run = store.run(args.run_id)
        for package in run["packages"]:
            marker = (package["status"], package["fetched"], package["rejected"])
            if marker != last.get(package["package_key"]):
                print("PROGRESS", package["package_key"], marker, flush=True)
                last[package["package_key"]] = marker
        active = [p for p in run["packages"] if p["status"] not in TERMINAL]
        if run["status"] not in {"queued", "running"} and not active:
            break
        if not worker.run_once():
            time.sleep(2)
    run = store.run(args.run_id)
    summary = {
        "run_id": args.run_id,
        "monitor_id": run["monitor_id"],
        "status": run["status"],
        "fetched": run.get("fetched"),
        "inserted": run.get("inserted"),
        "updated": run.get("updated"),
        "unchanged": run.get("unchanged"),
        "rejected": run.get("rejected"),
        "packages": [
            {key: package.get(key) for key in (
                "package_key", "status", "fetched", "inserted", "updated", "unchanged",
                "rejected", "error_code", "error_message", "execution_id",
            )}
            for package in run["packages"]
        ],
    }
    result_path = Path(args.result) if args.result else ROOT / ".local" / f"run-{args.run_id}-result.json"
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.archive_monitor:
        store.archive_monitor(run["monitor_id"])
    print("FINAL", json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
