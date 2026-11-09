import unittest
from unittest.mock import MagicMock, Mock

import pymysql

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.storage import MonitorNameConflict, PlatformStore, monitor_name_key


class MonitorArchiveTests(unittest.TestCase):
    def setUp(self):
        self.store = PlatformStore(SETTINGS)
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.store.connect = Mock(return_value=self.connection)

    def test_name_key_normalizes_case_width_and_whitespace(self):
        self.assertEqual(monitor_name_key(" AI  Monitor "), monitor_name_key("ａｉ monitor"))
        self.assertNotEqual(monitor_name_key("AI monitor"), monitor_name_key("AI monitoring"))

    def test_list_separates_active_and_archived(self):
        row = {
            "id": 3, "aliases_json": "[]", "selected_categories_json": "[]",
            "active_name_key": None,
        }
        self.cursor.fetchall.side_effect = [[row.copy()], [row.copy()]]
        self.assertEqual(3, self.store.list_monitors("archived")[0]["id"])
        self.assertIn("archived_at IS NOT NULL", self.cursor.execute.call_args.args[0])
        self.assertNotIn("active_name_key", self.store.list_monitors("all")[0])
        with self.assertRaises(ValueError):
            self.store.list_monitors("deleted")

    def test_archive_blocks_active_collection_without_changing_monitor(self):
        self.cursor.fetchone.side_effect = [{"id": 3, "archived_at": None}, {"id": 44}]
        with self.assertRaisesRegex(ValueError, "active collection"):
            self.store.archive_monitor(3)
        self.connection.rollback.assert_called_once()
        self.assertFalse(any("UPDATE monitors SET archived_at" in call.args[0]
                             for call in self.cursor.execute.call_args_list))

    def test_archive_stops_schedule_and_pending_report(self):
        self.cursor.fetchone.side_effect = [{"id": 3, "archived_at": None}, None, None]
        self.store.archive_monitor(3)
        sql = "\n".join(call.args[0] for call in self.cursor.execute.call_args_list)
        self.assertIn("enabled=0,next_run_at=NULL", sql)
        self.assertIn("status='cancelled'", sql)
        self.connection.commit.assert_called_once()

    def test_restore_is_disabled_and_can_be_renamed(self):
        self.cursor.fetchone.return_value = {"id": 3, "name": "大模型", "archived_at": object()}
        self.store.restore_monitor(3, "大模型-旧任务")
        sql, params = self.cursor.execute.call_args.args
        self.assertIn("enabled=0,next_run_at=NULL", sql)
        self.assertEqual("大模型-旧任务", params[0])
        self.assertEqual(monitor_name_key("大模型-旧任务"), params[1])

    def test_restore_conflict_rolls_back(self):
        self.cursor.fetchone.return_value = {"id": 3, "name": "大模型", "archived_at": object()}
        self.cursor.execute.side_effect = [None, pymysql.IntegrityError(1062, "duplicate")]
        with self.assertRaises(MonitorNameConflict):
            self.store.restore_monitor(3)
        self.connection.rollback.assert_called_once()

    def test_create_conflict_is_reported_from_unique_index(self):
        self.cursor.execute.side_effect = pymysql.IntegrityError(1062, "duplicate")
        with self.assertRaises(MonitorNameConflict):
            self.store.create_monitor("AI", "AI", [], [], None)
        self.connection.rollback.assert_called_once()

    def test_migration_rejects_legacy_duplicate_without_auto_archiving(self):
        self.cursor.fetchall.side_effect = [
            [{"COLUMN_NAME": "archived_at"}, {"COLUMN_NAME": "active_name_key"}],
            [{"id": 3, "name": "大模型", "archived_at": None, "active_name_key": None},
             {"id": 13, "name": "大模型", "archived_at": None, "active_name_key": None}],
        ]
        with self.assertRaisesRegex(ValueError, "#3 and #13"):
            self.store._migrate_monitor_archive()
        self.connection.rollback.assert_called_once()
        self.assertFalse(any("UPDATE monitors" in call.args[0] for call in self.cursor.execute.call_args_list))

    def test_archived_monitor_cannot_enqueue_or_schedule(self):
        self.cursor.fetchone.return_value = {"id": 3, "enabled": 1, "archived_at": object()}
        with self.assertRaisesRegex(ValueError, "disabled"):
            self.store.enqueue_monitor(3)
        with self.assertRaisesRegex(ValueError, "archived"):
            self.store.update_monitor_schedule(3, "manual", None)

    def test_api_archive_restore_and_conflict_status(self):
        store = Mock()
        client = create_app(SETTINGS, store).test_client()
        self.assertEqual(200, client.post("/api/v1/monitors/3/archive").status_code)
        store.archive_monitor.assert_called_once_with(3)
        self.assertEqual(200, client.post("/api/v1/monitors/3/restore", json={
            "name": "旧大模型",
        }).status_code)
        store.restore_monitor.assert_called_once_with(3, "旧大模型")
        self.assertEqual(422, client.post("/api/v1/monitors/3/restore", json={
            "enabled": True,
        }).status_code)
        store.restore_monitor.side_effect = MonitorNameConflict("active monitor name already exists")
        self.assertEqual(409, client.post("/api/v1/monitors/3/restore", json={}).status_code)
        client.get("/api/v1/monitors?status=archived")
        store.list_monitors.assert_called_with("archived")


if __name__ == "__main__":
    unittest.main()
