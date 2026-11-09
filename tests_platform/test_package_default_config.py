import unittest
from unittest.mock import Mock, patch

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.protocol import ProtocolError
from crawler_platform.storage import PlatformStore, json_dump


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "enabled": {"type": "boolean", "default": True},
        "pages": {"type": "integer", "minimum": 1, "maximum": 10, "default": 2},
        "sites": {"type": "array", "items": {"enum": ["a", "b"]}},
    },
}


class PackageDefaultConfigTests(unittest.TestCase):
    def setUp(self):
        self.store = PlatformStore(SETTINGS)
        self.connection = Mock()
        self.cursor = Mock()
        self.connection.cursor.return_value.__enter__ = Mock(return_value=self.cursor)
        self.connection.cursor.return_value.__exit__ = Mock(return_value=False)
        self.cursor.fetchone.return_value = {
            "name": "Example", "manifest_json": json_dump({"parameters_schema": SCHEMA}),
        }
        self.client = create_app(SETTINGS, self.store).test_client()

    def test_get_uses_saved_values_and_schema_defaults(self):
        with patch.object(self.store, "package", return_value={
            "name": "Example", "manifest": {"parameters_schema": SCHEMA},
            "default_config": {"enabled": False},
        }):
            response = self.client.get("/api/v1/packages/example/default-config")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"enabled": False, "pages": 2}, response.get_json()["config"])

    def test_put_validates_and_commits_config(self):
        with patch.object(self.store, "connect", return_value=self.connection):
            response = self.client.put("/api/v1/packages/example/default-config", json={
                "config": {"enabled": False, "pages": 5, "sites": ["b"]},
            })
        self.assertEqual(200, response.status_code)
        self.assertEqual(False, response.get_json()["config"]["enabled"])
        self.connection.commit.assert_called_once()
        self.assertEqual(2, self.cursor.execute.call_count)
        self.assertIn('"pages":5', self.cursor.execute.call_args.args[1][0])

    def test_invalid_parameters_rollback_without_update(self):
        for config in ({"pages": 11}, {"sites": ["unknown"]}, {"unknown": True}, []):
            with self.subTest(config=config):
                self.cursor.reset_mock()
                self.connection.reset_mock()
                with patch.object(self.store, "connect", return_value=self.connection):
                    with self.assertRaises(ProtocolError):
                        self.store.update_package_default_config("example", config)
                self.connection.rollback.assert_called_once()
                self.connection.commit.assert_not_called()
                self.assertEqual(1, self.cursor.execute.call_count)

    def test_unknown_package_is_not_found(self):
        self.cursor.fetchone.return_value = None
        with patch.object(self.store, "connect", return_value=self.connection):
            response = self.client.put("/api/v1/packages/missing/default-config", json={"config": {}})
        self.assertEqual(404, response.status_code)
        self.connection.commit.assert_not_called()

    def test_new_monitor_uses_defaults_and_task_overrides_take_priority(self):
        self.cursor.fetchall.return_value = [{
            "id": 3, "package_key": "example",
            "manifest_json": json_dump({"parameters_schema": SCHEMA}),
            "default_config_json": json_dump({"enabled": False, "pages": 5}),
        }]
        for override, expected in (({}, 5), ({"pages": 7}, 7)):
            with self.subTest(override=override):
                self.cursor.reset_mock()
                with patch.object(self.store, "connect", return_value=self.connection):
                    self.store.create_monitor("Example", "AI", [], [], None, package_settings=[{
                        "package_key": "example", "config": override,
                    }])
                stored = self.cursor.execute.call_args.args[1][-1]
                self.assertIn('"enabled":false', stored)
                self.assertIn(f'"pages":{expected}', stored)

    def test_put_rejects_missing_or_unknown_envelope_fields(self):
        for body in ({}, {"config": {}, "extra": 1}, []):
            with self.subTest(body=body):
                response = self.client.put("/api/v1/packages/example/default-config", json=body)
                self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
