"""Upgrade RSS after checking idleness; verify defaults, links and table are preserved."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.importer import PackageImporter
from crawler_platform.protocol import load_manifest, validate_parameters
from crawler_platform.storage import PlatformStore


def main():
    store = PlatformStore(SETTINGS)
    importer = PackageImporter(SETTINGS, store)
    source = ROOT / "crawler_packages/news/rss_multi_feed"
    manifest = load_manifest(source)
    before = store.package("rss_multi_feed")
    store.assert_package_idle("rss_multi_feed")

    def settings_snapshot(package_id):
        connection = store.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT monitor_id,enabled,item_limit,config_json FROM monitor_packages "
                               "WHERE package_id=%s ORDER BY monitor_id", (package_id,))
                return list(cursor.fetchall())
        finally:
            connection.close()

    prior_settings = settings_snapshot(before["id"])
    expected_defaults = validate_parameters(manifest.parameters_schema, before["default_config"])
    result = importer.install(source)
    after = store.package("rss_multi_feed")
    assert after["table_name"] == before["table_name"]
    assert after["default_config"] == expected_defaults
    assert settings_snapshot(after["id"]) == prior_settings
    health = importer.environment_health(manifest, Path(after["active_artifact_path"]))
    assert health["healthy"]
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    report = {"checked_at_beijing": stamp, "status": "passed", "old_version": before["active_version"],
              "new_version": after["active_version"], "table": after["table_name"], "table_preserved": True,
              "defaults_preserved": True, "monitor_settings_preserved": True,
              "monitor_settings_count": len(prior_settings), "feed_count": len(after["default_config"]["feed_urls"]),
              "keyword_policy": after["default_config"]["keyword_policy"], "environment_healthy": True,
              "settings_digest": hashlib.sha256(json.dumps(prior_settings, sort_keys=True).encode()).hexdigest(),
              "created_monitors": 0, "result": result}
    output = ROOT / "reports" / f"rss-upgrade-{stamp}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(output)


if __name__ == "__main__":
    main()
