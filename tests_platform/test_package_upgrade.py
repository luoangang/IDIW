import json
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from crawler_platform.config import SETTINGS
from crawler_platform.protocol import ProtocolError, load_manifest
from crawler_platform.storage import PlatformStore, json_dump


MANIFEST = load_manifest(Path(__file__).resolve().parents[1] / "crawler_packages/news/rss_multi_feed")


def setup_upgrade(defaults=None):
    store = PlatformStore(SETTINGS)
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    existing = {"id": 7, "active_version": "1.0.0", "artifact_digest": "old", "status": "ready",
                "table_name": "pkg_data_000007", "name": "Custom RSS", "description": "old description",
                "category": "news", "protocol_version": "1.0", "manifest_json": json_dump(MANIFEST.raw),
                "default_config_json": json_dump(defaults or {"feed_urls": ["https://custom.example/feed"], "lookback_days": 7})}
    cursor.fetchone.side_effect = [existing, None]
    cursor.fetchall.return_value = []
    store.connect = Mock(return_value=connection)
    return store, connection, cursor, existing


def test_upgrade_preserves_custom_defaults_and_backs_up_active_metadata():
    store, connection, cursor, existing = setup_upgrade()
    result = store.register_installing(MANIFEST, "new-digest", "schema", Path("artifact"))
    sql, values = cursor.execute.call_args.args
    assert "UPDATE crawler_packages" in sql
    defaults = json.loads(values[5])
    assert defaults["feed_urls"] == ["https://custom.example/feed"]
    assert defaults["lookback_days"] == 7
    assert defaults["keyword_policy"] == "union"
    assert json.loads(values[6])["previous"]["default_config_json"] == existing["default_config_json"]
    assert result["table_name"] == "pkg_data_000007"
    connection.commit.assert_called_once()


def test_busy_package_cannot_be_marked_installing():
    store, connection, cursor, existing = setup_upgrade()
    cursor.fetchone.side_effect = [existing, {"id": 42}]
    with pytest.raises(ValueError, match="queued or running"):
        store.register_installing(MANIFEST, "new", "schema", Path("artifact"))
    assert not any("UPDATE crawler_packages" in call.args[0] for call in cursor.execute.call_args_list)
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


def test_incompatible_defaults_or_monitor_settings_block_upgrade():
    store, connection, cursor, _ = setup_upgrade({"feed_urls": ["file:///private"]})
    with pytest.raises(ProtocolError):
        store.register_installing(MANIFEST, "new", "schema", Path("artifact"))
    connection.commit.assert_not_called()
    store, connection, cursor, _ = setup_upgrade()
    cursor.fetchall.return_value = [{"monitor_id": 8, "config_json": '{"timeout_seconds":9999}'}]
    with pytest.raises(ProtocolError, match="monitor #8"):
        store.register_installing(MANIFEST, "new", "schema", Path("artifact"))
    connection.commit.assert_not_called()


def test_failed_upgrade_restores_previous_metadata_and_keeps_old_version_ready():
    store, connection, cursor, previous = setup_upgrade()
    cursor.fetchone.side_effect = None
    cursor.fetchone.return_value = {"active_version": "1.0.0", "install_state_json": json_dump({"previous": previous})}
    store.fail_install("rss_multi_feed", "dependency installation failed")
    sql, values = cursor.execute.call_args.args
    assert "status='ready'" in sql
    assert values[0] == "Custom RSS"
    assert values[5] == previous["default_config_json"]
    assert json.loads(values[6])["stage"] == "upgrade_failed"
    connection.commit.assert_called_once()


def test_failed_first_install_stays_failed_without_fake_ready_version():
    store, connection, cursor, _ = setup_upgrade()
    cursor.fetchone.side_effect = None
    cursor.fetchone.return_value = {"active_version": None, "install_state_json": '{}'}
    store.fail_install("rss_multi_feed", "failed")
    assert "status='install_failed'" in cursor.execute.call_args.args[0]


def test_defaults_cannot_be_changed_during_upgrade():
    store, connection, cursor, existing = setup_upgrade()
    cursor.fetchone.side_effect = None
    cursor.fetchone.return_value = {**existing, "status": "installing"}
    with pytest.raises(ValueError, match="installation is in progress"):
        store.update_package_default_config("rss_multi_feed", {"feed_urls": ["https://new.example/feed"]})
    assert not any("UPDATE crawler_packages" in call.args[0] for call in cursor.execute.call_args_list)
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
