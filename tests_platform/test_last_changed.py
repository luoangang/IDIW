import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from crawler_platform.config import SETTINGS
from crawler_platform.protocol import FieldSpec, content_digest
from crawler_platform.storage import PlatformStore

SINCE = "2026-11-25T08:00:00+08:00"
SINCE_UTC = datetime(2026, 11, 25, 0, 0, 0)
TABLE = "pkg_data_000003"


def field(name: str) -> FieldSpec:
    return FieldSpec(name=name, type="string", nullable=False, max_length=200)


def manifest_stub() -> SimpleNamespace:
    fields = (field("title"), field("url"))
    return SimpleNamespace(
        fields=fields,
        field_map={spec.name: spec for spec in fields},
        identity_fields=("url",),
        indexes=(),
        mapping={"title": "title", "url": "url"},
    )


class CreateTableSqlTests(unittest.TestCase):
    def test_new_tables_include_change_tracking_columns_and_index(self):
        store = PlatformStore(SETTINGS)
        sql = store._create_table_sql("pkg_data_000123", manifest_stub())
        self.assertIn("sys_last_seen_at DATETIME(6) NOT NULL,sys_last_changed_at DATETIME(6) NULL", sql)
        self.assertIn("sys_last_changed_at DATETIME(6) NULL,"
                      "sys_change_count INT UNSIGNED NOT NULL DEFAULT 0", sql)
        self.assertIn("INDEX idx_last_changed (sys_last_changed_at,sys_id)", sql)


class PreviewChangeFilterTests(unittest.TestCase):
    def setUp(self):
        self.store = PlatformStore(SETTINGS)
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.package = {"id": 3, "package_key": "example", "name": "Example",
                        "table_name": TABLE, "active_artifact_path": "example"}

    def preview(self, **kwargs):
        rows = [{"total": 1}]
        if kwargs.get("monitor_id") is not None:
            rows.insert(0, {"id": kwargs["monitor_id"]})
        self.cursor.fetchone.side_effect = rows
        self.cursor.fetchall.side_effect = [[self.package], [{"title": "Match"}]]
        with patch.object(self.store, "connect", return_value=self.connection), \
             patch("crawler_platform.storage.load_manifest", return_value=manifest_stub()):
            self.store.preview_records(**kwargs)
        return [(call.args[0], call.args[1]) for call in self.cursor.execute.call_args_list]

    def select_call(self, calls):
        query, values = calls[-1]
        self.assertIn("SELECT * FROM (SELECT", query)
        self.assertIn(") records ORDER BY last_seen_at DESC", query)
        return query, values

    def count_call(self, calls):
        for query, values in calls:
            if query.startswith("SELECT SUM(n) AS total"):
                return query, values
        raise AssertionError("count query not executed")

    def test_updated_filter_and_markers_use_since_in_order(self):
        calls = self.preview(monitor_id=7, query="AI", since=SINCE, change="updated")
        query, values = self.select_call(calls)
        self.assertIn("(r.sys_first_seen_at >= %s) AS is_new", query)
        self.assertIn("(r.sys_last_changed_at >= %s AND r.sys_first_seen_at < %s) AS is_updated", query)
        self.assertIn("WHERE r.`title` LIKE %s AND r.sys_last_changed_at >= %s "
                      "AND r.sys_first_seen_at < %s", query)
        self.assertEqual(["example", "Example"], values[:2])
        self.assertEqual([SINCE_UTC] * 3, values[2:5])
        self.assertEqual([3, 7], values[5:7])
        self.assertEqual("%AI%", values[7])
        self.assertEqual([SINCE_UTC, SINCE_UTC], values[8:10])
        self.assertEqual([25, 0], values[-2:])
        count_query, count_values = self.count_call(calls)
        self.assertIn("r.sys_last_changed_at >= %s AND r.sys_first_seen_at < %s", count_query)
        self.assertEqual([3, 7, "%AI%", SINCE_UTC, SINCE_UTC], count_values)

    def test_new_filter_only_constrains_first_seen(self):
        calls = self.preview(since="2026-11-25T00:00:00Z", change="new")
        query, values = self.select_call(calls)
        self.assertIn(f"FROM `{TABLE}` r WHERE r.sys_first_seen_at >= %s", query)
        self.assertEqual(1, query.count(" WHERE "))
        self.assertEqual(["example", "Example"], values[:2])
        self.assertEqual([SINCE_UTC] * 4, values[2:6])
        self.assertEqual([25, 0], values[-2:])

    def test_changed_filter_uses_last_changed_only(self):
        calls = self.preview(since=SINCE, change="changed")
        query, values = self.select_call(calls)
        self.assertIn(f"FROM `{TABLE}` r WHERE r.sys_last_changed_at >= %s", query)
        self.assertEqual([SINCE_UTC] * 4, values[2:6])
        self.assertEqual([25, 0], values[-2:])
        _, count_values = self.count_call(calls)
        self.assertEqual([SINCE_UTC], count_values)

    def test_since_without_change_only_marks_rows(self):
        calls = self.preview(since=SINCE)
        query, values = self.select_call(calls)
        self.assertIn("(r.sys_first_seen_at >= %s) AS is_new", query)
        self.assertNotIn(" WHERE ", query)
        self.assertEqual([SINCE_UTC] * 3, values[2:5])
        self.assertEqual([25, 0], values[-2:])
        _, count_values = self.count_call(calls)
        self.assertEqual([], count_values)

    def test_no_since_keeps_legacy_query_shape(self):
        calls = self.preview(query="AI")
        query, values = self.select_call(calls)
        self.assertIn("NULL AS is_new,NULL AS is_updated", query)
        self.assertNotIn("sys_last_changed_at >=", query)
        self.assertIn("r.sys_first_seen_at AS first_seen_at", query)
        self.assertIn("r.sys_last_changed_at AS last_changed_at", query)
        self.assertEqual(["example", "Example", "%AI%", 25, 0], values)

    def test_invalid_change_or_since_is_rejected_before_connecting(self):
        with patch.object(self.store, "connect") as connect:
            for kwargs in ({"change": "stale", "since": SINCE},
                           {"change": "new"},
                           {"change": "updated"},
                           {"change": "NEW", "since": SINCE},
                           {"since": "not-a-timestamp"},
                           {"since": ""},
                           {"since": 20261125},
                           {"since": SINCE, "change": ""}):
                with self.assertRaises(ValueError):
                    self.store.preview_records(**kwargs)
            connect.assert_not_called()

    def test_timezone_aware_since_is_converted_to_utc_and_naive(self):
        self.assertEqual(SINCE_UTC, self.store._parse_since("2026-11-25T00:00:00Z"))
        self.assertEqual(SINCE_UTC, self.store._parse_since("2026-11-25T00:00:00"))
        self.assertEqual(SINCE_UTC, self.store._parse_since("2026-11-25T08:00:00+08:00"))
        calls = self.preview(since=SINCE)
        _, values = self.select_call(calls)
        self.assertEqual(SINCE_UTC, values[2])
        self.assertIsNone(values[2].tzinfo)


class IngestChangeTrackingTests(unittest.TestCase):
    def setUp(self):
        self.store = PlatformStore(SETTINGS)
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.manifest = manifest_stub()
        self.claimed = {
            "id": 11, "table_name": TABLE, "lease_token": "lease",
            "monitor_id": 7, "package_id": 3, "request": {"cursor_version": 0},
            "run_id": 5, "attempt_no": 1, "package_version": "1.0.0",
            "schema_version": 1, "artifact_digest": "d" * 64, "artifact_path": "example",
        }

    def ingest(self, existing, item):
        self.cursor.fetchone.side_effect = [
            {"status": "running", "lease_token": "lease"},
            {"cursor_version": 0},
            existing,
        ]
        result = {"status": "completed", "warnings": []}
        with patch.object(self.store, "connect", return_value=self.connection), \
             patch.object(self.store, "finalize_parent_for_package_run"):
            stats = self.store.ingest(self.claimed, self.manifest, [item], 0, result, 0,
                                      "work", "log")
        return stats, [(call.args[0], call.args[1]) for call in self.cursor.execute.call_args_list]

    def test_new_record_starts_change_tracking(self):
        stats, calls = self.ingest(None, {"title": "Fresh", "url": "https://example.test/a"})
        self.assertEqual(1, stats["inserted"])
        insert, values = next((q, v) for q, v in calls if q.startswith(f"INSERT INTO `{TABLE}`"))
        self.assertIn("sys_last_changed_at", insert)
        self.assertIn("sys_change_count", insert)
        self.assertEqual(1, values[-1])
        self.assertEqual(values[-2], values[-3])

    def test_changed_record_advances_change_timestamp_and_counter(self):
        existing = {"sys_id": 42, "sys_resource_uid": "uid-42",
                    "sys_content_hash": content_digest({"title": "Old", "url": "https://example.test/a"}),
                    "title": "Old", "url": "https://example.test/a"}
        stats, calls = self.ingest(existing, {"title": "New", "url": "https://example.test/a"})
        self.assertEqual(1, stats["updated"])
        update, values = next((q, v) for q, v in calls if q.startswith(f"UPDATE `{TABLE}` SET"))
        self.assertIn("sys_last_changed_at=%s", update)
        self.assertIn("sys_change_count=sys_change_count+1", update)
        self.assertIn("sys_last_seen_at=%s", update)
        self.assertEqual(42, values[-1])
        self.assertEqual(values[-2], values[-3])

    def test_unchanged_record_keeps_change_timestamp_and_counter(self):
        existing = {"sys_id": 42, "sys_resource_uid": "uid-42",
                    "sys_content_hash": content_digest({"title": "Same", "url": "https://example.test/a"}),
                    "title": "Same", "url": "https://example.test/a"}
        stats, calls = self.ingest(existing, {"title": "Same", "url": "https://example.test/a"})
        self.assertEqual(1, stats["unchanged"])
        update, values = next((q, v) for q, v in calls if q.startswith(f"UPDATE `{TABLE}` SET"))
        self.assertNotIn("sys_last_changed_at", update)
        self.assertNotIn("sys_change_count", update)
        self.assertIn("sys_last_seen_at=%s", update)
        self.assertEqual(42, values[-1])


if __name__ == "__main__":
    unittest.main()
