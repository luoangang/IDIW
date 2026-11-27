from __future__ import annotations

import json
from pathlib import Path

from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "crawler_packages" / "academic"
PACKAGES = [
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
STATE = ROOT / ".local" / "platform-domestic-full-test-2026-11-25.json"


def main():
    store = PlatformStore(SETTINGS)
    existing = {row["name"] for row in store.list_monitors("all")}
    name = "国内全量-最新一期-2026-11-25"
    if name in existing:
        raise SystemExit(f"monitor already exists: {name}")
    settings = []
    for package_key in PACKAGES:
        package_dir = ACADEMIC / package_key
        manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
        properties = manifest["parameters_schema"]["properties"]
        journals = json.loads((package_dir / "journals.json").read_text(encoding="utf-8"))
        keys = [row["journal_key"] for row in journals]
        config = {
            "journal_keys": keys,
            "collect_mode": "latest_issue",
        }
        if "per_journal_limit" in properties:
            config["per_journal_limit"] = 2
        if "timeout_seconds" in properties:
            config["timeout_seconds"] = 15
        if "enrich_abstract" in properties:
            config["enrich_abstract"] = False
        if "abstract_enrich_limit" in properties:
            config["abstract_enrich_limit"] = 0
        if "request_delay_ms" in properties:
            config["request_delay_ms"] = 0
        if "follow_latest" in properties:
            config["follow_latest"] = True
        settings.append({
            "package_key": package_key,
            "enabled": True,
            "item_limit": min(10000, max(1, len(keys) * 2)),
            "config": config,
        })
        print(package_key, len(keys), "item_limit", min(10000, max(1, len(keys) * 2)))
    monitor_id = store.create_monitor(
        name=name,
        query="最新一期",
        aliases=[],
        categories=[],
        package_keys=[row["package_key"] for row in settings],
        schedule_type="manual",
        package_settings=settings,
    )
    run_id = store.enqueue_monitor(monitor_id)
    state = {"monitor_id": monitor_id, "run_id": run_id, "name": name, "packages": PACKAGES}
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("monitor_id", monitor_id, "run_id", run_id, "state", STATE)


if __name__ == "__main__":
    main()
