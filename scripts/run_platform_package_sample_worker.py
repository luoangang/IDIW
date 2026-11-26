from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import Settings
from crawler_platform.executor import Worker
from crawler_platform.storage import PlatformStore


STATE = ROOT / ".local" / "platform-package-sample-test-2026-11-25.json"
RESULT = ROOT / ".local" / "platform-package-sample-test-2026-11-25-result.json"
TERMINAL_PACKAGE = {"completed", "partial", "failed", "timed_out", "cancelled"}


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    run_id, monitor_id = state["run_id"], state["monitor_id"]
    settings = Settings(package_timeout_seconds=300, worker_poll_seconds=2)
    store = PlatformStore(settings)
    worker = Worker(settings, store)
    last: dict[str, tuple] = {}
    while True:
        run = store.run(run_id)
        packages = run["packages"]
        for package in packages:
            marker = (package["status"], package["fetched"], package["rejected"])
            if marker != last.get(package["package_key"]):
                print("PROGRESS", package["package_key"], marker, flush=True)
                last[package["package_key"]] = marker
        active = [p for p in packages if p["status"] not in TERMINAL_PACKAGE]
        if run["status"] not in {"queued", "running"} and not active:
            break
        if not worker.run_once():
            time.sleep(2)
    run = store.run(run_id)
    summary = {
        "monitor_id": monitor_id,
        "run_id": run_id,
        "status": run["status"],
        "fetched": run.get("fetched"),
        "inserted": run.get("inserted"),
        "updated": run.get("updated"),
        "unchanged": run.get("unchanged"),
        "rejected": run.get("rejected"),
        "packages": [
            {
                "package_key": package["package_key"],
                "status": package["status"],
                "fetched": package["fetched"],
                "inserted": package["inserted"],
                "updated": package["updated"],
                "unchanged": package["unchanged"],
                "rejected": package["rejected"],
                "error_code": package["error_code"],
                "error_message": package["error_message"],
                "started_at": str(package["started_at"]),
                "finished_at": str(package["finished_at"]),
            }
            for package in run["packages"]
        ],
    }
    RESULT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    store.archive_monitor(monitor_id)
    print("FINAL", json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
