import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.request import getproxies

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.executor import PackageExecutor
from crawler_platform.proxy_pool import check_proxy_connection, proxy_environment, validate_proxy_url
from crawler_platform.storage import PlatformStore


class ProxyPoolTests(unittest.TestCase):
    def test_only_credential_free_http_proxy_urls_are_accepted(self):
        self.assertEqual("http://127.0.0.1:8080", validate_proxy_url("http://127.0.0.1:8080"))
        for value in ("https://proxy.example:8080", "http://user:secret@proxy.example:8080",
                      "http://proxy.example", "http://proxy.example:0", "http://proxy.example:8080/path",
                      "http://proxy.example:8080?x=1", " http://proxy.example:8080"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_proxy_url(value)

    def test_proxy_environment_covers_urllib_and_common_http_clients(self):
        env = proxy_environment("http://127.0.0.1:8080")
        self.assertEqual(env["http_proxy"], env["HTTP_PROXY"])
        self.assertEqual(env["https_proxy"], env["HTTPS_PROXY"])
        self.assertIn("127.0.0.1", env["no_proxy"])
        with patch.dict("os.environ", env, clear=True):
            self.assertEqual("http://127.0.0.1:8080", getproxies()["https"])

    def test_subprocess_urllib_receives_proxy(self):
        env = PackageExecutor._child_environment(Path(sys.executable), SETTINGS.runs_dir)
        env.update(proxy_environment("http://127.0.0.1:8080"))
        output = subprocess.check_output(
            [sys.executable, "-c", "import json,urllib.request; print(json.dumps(urllib.request.getproxies()))"],
            env=env, text=True, timeout=10,
        )
        self.assertEqual("http://127.0.0.1:8080", json.loads(output)["https"])

    def test_management_api_validates_before_writing(self):
        store = Mock()
        store.list_proxies.return_value = []
        app = create_app(SETTINGS, store)
        with app.test_client() as client:
            headers = {"Authorization": f"Bearer {SETTINGS.token}"} if SETTINGS.token else {}
            self.assertEqual([], client.get("/api/v1/proxies", headers=headers).get_json())
            response = client.post("/api/v1/proxies", json={"name": "node"}, headers=headers)
            self.assertEqual(422, response.status_code)
            store.create_proxy.assert_not_called()

    def test_connection_check_only_tests_tcp_port(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        with patch("crawler_platform.proxy_pool.socket.create_connection", return_value=connection) as create:
            self.assertTrue(check_proxy_connection("http://proxy.example:8080"))
        create.assert_called_once_with(("proxy.example", 8080), timeout=3.0)

    def test_assign_proxy_records_the_selected_node(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        selected = {"id": 7, "name": "node", "proxy_url": "http://proxy.example:8080"}
        cursor.fetchone.side_effect = [None, selected]
        connection = Mock()
        connection.cursor.return_value = cursor
        store = PlatformStore(SETTINGS)
        store.connect = Mock(return_value=connection)
        self.assertEqual(selected, store.assign_proxy(42))
        self.assertTrue(any("INSERT INTO proxy_run_assignments" in call.args[0]
                            for call in cursor.execute.call_args_list))
        connection.commit.assert_called_once()

    def test_assign_proxy_keeps_direct_connection_when_pool_is_empty(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        cursor.fetchone.side_effect = [None, None]
        connection = Mock()
        connection.cursor.return_value = cursor
        store = PlatformStore(SETTINGS)
        store.connect = Mock(return_value=connection)
        self.assertIsNone(store.assign_proxy(42))
        self.assertFalse(any("INSERT INTO proxy_run_assignments" in call.args[0]
                             for call in cursor.execute.call_args_list))

    def test_used_proxy_address_cannot_change(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        cursor.fetchone.return_value = {"proxy_url": "http://old.example:8080", "selected_count": 2}
        connection = Mock()
        connection.cursor.return_value = cursor
        store = PlatformStore(SETTINGS)
        store.connect = Mock(return_value=connection)
        with self.assertRaisesRegex(ValueError, "cannot change"):
            store.update_proxy(7, "node", "http://new.example:8080", True)
        connection.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
