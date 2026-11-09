import unittest

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore


class FakeStore:
    def __init__(self):
        self.created = None
        self.updated = None

    def create_monitor(self, **kwargs):
        self.created = kwargs
        return 17

    def monitor_package_settings(self, monitor_id):
        return [{"package_key": "wikipedia", "enabled": True, "item_limit": 12}]

    def update_monitor_packages(self, monitor_id, packages):
        self.updated = (monitor_id, packages)
        return packages


class MonitorPackageApiTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.client = create_app(SETTINGS, self.store).test_client()

    def test_create_monitor_accepts_per_package_settings(self):
        packages = [{
            "package_key": "wikipedia", "enabled": True,
            "item_limit": 12, "config": {"english_fallback": False},
        }]
        response = self.client.post("/api/v1/monitors", json={
            "name": "AI", "query": "人工智能", "packages": packages,
        })
        self.assertEqual(201, response.status_code)
        self.assertEqual({"id": 17}, response.get_json())
        self.assertEqual(packages, self.store.created["package_settings"])
        self.assertIsNone(self.store.created["package_keys"])

    def test_get_monitor_package_settings(self):
        response = self.client.get("/api/v1/monitors/8/packages")
        self.assertEqual(200, response.status_code)
        self.assertEqual(12, response.get_json()[0]["item_limit"])

    def test_update_monitor_package_settings(self):
        packages = [{
            "package_key": "wikipedia", "enabled": False,
            "item_limit": 50, "config": {"english_fallback": True},
        }]
        response = self.client.put("/api/v1/monitors/8/packages", json={"packages": packages})
        self.assertEqual(200, response.status_code)
        self.assertEqual((8, packages), self.store.updated)


class ItemLimitTests(unittest.TestCase):
    def test_item_limit_range(self):
        self.assertEqual(1, PlatformStore._item_limit(1))
        self.assertEqual(10000, PlatformStore._item_limit(10000))
        for value in (True, 0, 10001, "10", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PlatformStore._item_limit(value)


if __name__ == "__main__":
    unittest.main()
