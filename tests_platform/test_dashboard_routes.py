import unittest

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS


class DashboardRouteTests(unittest.TestCase):
    def test_direct_page_links_are_served_without_database_access(self):
        client = create_app(SETTINGS, object()).test_client()
        for path in ("/", "/sources", "/monitors", "/monitors/new",
                     "/monitors/5/sources", "/runs?monitor=5", "/runs/10", "/data?monitor=5",
                     "/reports", "/reports/4", "/assistant"):
            with self.subTest(path=path):
                with client.get(path) as response:
                    self.assertEqual(200, response.status_code)
                    self.assertTrue(response.content_type.startswith("text/html"))


if __name__ == "__main__":
    unittest.main()
