"""Opt in with PLATFORM_TEST_MYSQL=1; only generated crawler_it_* databases are modified."""

import os
import re
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crawler_platform.config import SETTINGS
from crawler_platform.protocol import load_manifest, package_digest, schema_digest
from crawler_platform.storage import PlatformStore


pytestmark = pytest.mark.skipif(os.getenv("PLATFORM_TEST_MYSQL") != "1", reason="opt-in isolated MySQL integration")
SOURCE = Path(__file__).resolve().parents[1] / "crawler_packages/news/rss_multi_feed"
MANIFEST = load_manifest(SOURCE)


@pytest.fixture
def database(tmp_path):
    name = "crawler_it_" + uuid.uuid4().hex
    assert re.fullmatch(r"crawler_it_[0-9a-f]{32}", name)
    settings = replace(SETTINGS, mysql_database=name, runtime_dir=tmp_path / "runtime")
    assert settings.mysql_database != SETTINGS.mysql_database
    store = PlatformStore(settings)
    try:
        store.initialize()
        digest, schema = package_digest(SOURCE), schema_digest(MANIFEST)
        row = store.register_installing(MANIFEST, digest, schema, SOURCE)
        store.create_or_upgrade_package_table(row["table_name"], MANIFEST)
        store.activate_package(row["id"], MANIFEST, digest, schema, SOURCE)
        yield store
    finally:
        # Never accept a database name from env, arguments, or application records for cleanup.
        assert name == settings.mysql_database and re.fullmatch(r"crawler_it_[0-9a-f]{32}", name)
        connection = store.connect(False)
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
            connection.commit()
        finally:
            connection.close()


def monitor(store, name="Integration", **kwargs):
    return store.create_monitor(name, "人工智能", ["artificial intelligence"], [],
                                [MANIFEST.package_key], **kwargs)


def complete(store, run_id, title="AI research"):
    claimed = store.claim_package_run("integration-worker")
    assert claimed and claimed["run_id"] == run_id
    assert store.renew_package_run_lease(claimed["id"], claimed["lease_token"])
    item = {"external_id": "article-1", "title": title, "url": "https://example.org/article-1",
            "content_scope": "feed_summary", "summary": "Example summary", "source_site": "example.org",
            "feed_url": "https://example.org/feed"}
    result = {"status": "completed", "item_count": 1, "next_cursor": None, "has_more": False,
              "warnings": [], "error": None}
    stats = store.ingest(claimed, MANIFEST, [item], 0, result, 0, Path("integration-run"), Path("process.log"))
    assert store.run(run_id)["status"] == "completed"
    return stats


def test_queue_ingestion_deduplication_and_monitor_relationships(database):
    store = database
    first = monitor(store)
    run_id = store.enqueue_monitor(first)
    with pytest.raises(ValueError, match="active run"):
        store.enqueue_monitor(first)
    assert complete(store, run_id)["inserted"] == 1
    assert complete(store, store.enqueue_monitor(first))["unchanged"] == 1
    second = monitor(store, "Other topic")
    assert complete(store, store.enqueue_monitor(second))["unchanged"] == 1
    assert len(store.package_records(MANIFEST.package_key)) == 1
    connection = store.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT monitor_id,match_count FROM monitor_resource_matches ORDER BY monitor_id")
            assert cursor.fetchall() == [{"monitor_id": first, "match_count": 2}, {"monitor_id": second, "match_count": 1}]
    finally:
        connection.close()
    store.archive_monitor(first)
    assert len(store.list_monitors("archived")) == 1
    assert len(store.package_records(MANIFEST.package_key)) == 1


def test_upgrade_preserves_defaults_rejects_busy_and_restores_failed_candidate(database):
    store = database
    saved = store.package_default_config(MANIFEST.package_key)["config"]
    saved.update(feed_urls=["https://custom.example.org/feed"], lookback_days=7)
    store.update_package_default_config(MANIFEST.package_key, saved)
    candidate = replace(MANIFEST, package_version="1.1.1", raw={**MANIFEST.raw, "package_version": "1.1.1"})
    store.register_installing(candidate, "a" * 64, schema_digest(candidate), SOURCE)
    assert store.package_default_config(MANIFEST.package_key)["config"] == saved
    with pytest.raises(ValueError, match="installation is in progress"):
        store.update_package_default_config(MANIFEST.package_key, saved)
    store.fail_install(MANIFEST.package_key, "simulated dependency failure")
    package = store.package(MANIFEST.package_key)
    assert package["status"] == "ready" and package["active_version"] == MANIFEST.package_version
    assert package["default_config"] == saved
    run_id = store.enqueue_monitor(monitor(store))
    with pytest.raises(ValueError, match="queued or running"):
        store.register_installing(candidate, "a" * 64, schema_digest(candidate), SOURCE)
    assert store.package(MANIFEST.package_key)["status"] == "ready"
    complete(store, run_id)


def test_due_schedule_is_caught_up_once_and_advances_beijing_slot(database):
    store = database
    monitor_id = monitor(store, schedule_type="daily", schedule_time="09:00")
    due = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
    connection = store.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE monitors SET next_run_at=%s WHERE id=%s", (due, monitor_id))
        connection.commit()
    finally:
        connection.close()
    assert store.operational_status()["overdue_monitors"] == 1
    runs = store.enqueue_due_monitors()
    assert len(runs) == 1
    assert store.enqueue_due_monitors() == []
    complete(store, runs[0])
    row = next(row for row in store.list_monitors() if row["id"] == monitor_id)
    assert row["next_run_at"] > datetime.now(timezone.utc).replace(tzinfo=None)
    assert (row["next_run_at"] + timedelta(hours=8)).time().isoformat() == "09:00:00"
    assert store.operational_status()["overdue_monitors"] == 0


def test_change_tracking_and_legacy_migration_are_idempotent(database):
    store = database
    monitor_id = monitor(store)
    complete(store, store.enqueue_monitor(monitor_id))
    table = store.package(MANIFEST.package_key)["table_name"]
    store._assert_table(table)

    def tracking():
        connection = store.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT sys_first_seen_at,sys_last_changed_at,sys_change_count FROM `{table}`")
                return cursor.fetchone()
        finally:
            connection.close()

    original = tracking()
    assert original["sys_change_count"] == 1
    assert complete(store, store.enqueue_monitor(monitor_id))["unchanged"] == 1
    assert tracking() == original
    assert complete(store, store.enqueue_monitor(monitor_id), "AI research updated")["updated"] == 1
    assert tracking()["sys_change_count"] == 2
    since = original["sys_first_seen_at"].replace(tzinfo=timezone.utc).isoformat()
    assert store.preview_records(since=since, change="changed")["total"] == 1
    # Recreate only the old system columns in this generated, isolated test database.
    connection = store.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE `{table}` DROP INDEX idx_last_changed, "
                           "DROP COLUMN sys_last_changed_at,DROP COLUMN sys_change_count")
        connection.commit()
    finally:
        connection.close()
    store._migrate_last_changed_at()
    migrated = tracking()
    assert migrated["sys_last_changed_at"] == migrated["sys_first_seen_at"]
    assert migrated["sys_change_count"] == 1
    store._migrate_last_changed_at()
    assert tracking() == migrated
