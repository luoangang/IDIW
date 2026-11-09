import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore


class DataPreviewTests(unittest.TestCase):
    def setUp(self):
        self.store = PlatformStore(SETTINGS)
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.package = {"id": 3, "package_key": "example", "name": "Example",
                        "table_name": "pkg_data_000003", "active_artifact_path": "example"}
        self.manifest = SimpleNamespace(mapping={"title": "title", "url": "url", "summary": "summary"})

    def test_combined_filters_count_and_paging_are_applied_in_database(self):
        self.cursor.fetchone.side_effect = [{"id": 7}, {"total": 12}]
        self.cursor.fetchall.side_effect = [[self.package], [{"title": "Match"}]]
        with patch.object(self.store, "connect", return_value=self.connection), \
             patch("crawler_platform.storage.load_manifest", return_value=self.manifest):
            result = self.store.preview_records(7, "example", "%_x", page=2, limit=2)
        self.assertEqual(12, result["total"])
        self.assertEqual(2, result["page"])
        query, values = self.cursor.execute.call_args.args
        self.assertIn("JOIN monitor_resource_matches", query)
        self.assertIn("ORDER BY last_seen_at DESC", query)
        self.assertNotIn("%_x", query)
        self.assertIn("%\\%\\_x%", values)
        self.assertEqual([2, 2], values[-2:])
        self.connection.close.assert_called_once()

    def test_no_installed_sources_is_empty(self):
        self.cursor.fetchall.return_value = []
        with patch.object(self.store, "connect", return_value=self.connection):
            result = self.store.preview_records()
        self.assertEqual([], result["items"])
        self.assertEqual(0, result["total"])

    def test_missing_monitor_does_not_return_unfiltered_records(self):
        self.cursor.fetchone.return_value = None
        with patch.object(self.store, "connect", return_value=self.connection):
            with self.assertRaises(KeyError):
                self.store.preview_records(monitor_id=999)

    def test_invalid_paging_is_rejected_before_connecting(self):
        with patch.object(self.store, "connect") as connect:
            for kwargs in ({"page": 0}, {"limit": 0}, {"limit": 101}):
                with self.assertRaises(ValueError):
                    self.store.preview_records(**kwargs)
            connect.assert_not_called()

    def test_detail_decodes_structured_fields_and_returns_task_associations(self):
        manifest = SimpleNamespace(mapping={"title": "title"},
                                   fields=[SimpleNamespace(name="authors", type="array")],
                                   raw={"output_schema": {"fields": [{"name": "authors", "type": "array"}]}})
        self.cursor.fetchone.return_value = {"title": "Paper", "authors": '["Alice"]',
                                            "sys_identity_hash": b"private", "sys_content_hash": b"private"}
        self.cursor.fetchall.return_value = [{"id": 7, "name": "AI"}]
        with patch.object(self.store, "package", return_value=self.package), \
             patch.object(self.store, "connect", return_value=self.connection), \
             patch("crawler_platform.storage.load_manifest", return_value=manifest):
            result = self.store.record_detail("example", "00000000-0000-0000-0000-000000000001")
        self.assertEqual(["Alice"], result["record"]["authors"])
        self.assertNotIn("sys_identity_hash", result["record"])
        self.assertEqual(7, result["monitors"][0]["id"])

    def test_api_passes_filters_and_rejects_invalid_page(self):
        store = MagicMock()
        store.preview_records.return_value = {"items": [], "total": 0, "page": 2, "limit": 25}
        client = create_app(SETTINGS, store).test_client()
        response = client.get("/api/v1/data?monitor=7&source=example&q=AI&page=2")
        self.assertEqual(200, response.status_code)
        store.preview_records.assert_called_once_with(monitor_id=7, package_key="example", query="AI", page=2, limit=25)
        self.assertEqual(422, client.get("/api/v1/data?page=invalid").status_code)


if __name__ == "__main__":
    unittest.main()
