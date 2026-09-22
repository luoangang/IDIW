import unittest
from decimal import Decimal

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore


class ApiJsonTests(unittest.TestCase):
    def test_decimal_records_are_encoded_as_strings(self):
        app = create_app(SETTINGS, PlatformStore(SETTINGS))
        with app.app_context():
            from crawler_platform.api import json_response
            response, status = json_response({"price": Decimal("12.30")})
        self.assertEqual(200, status)
        self.assertEqual({"price": "12.30"}, response.get_json())


if __name__ == "__main__":
    unittest.main()
