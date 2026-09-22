import unittest

from crawler_platform.storage import cursor_is_stalled


class CursorTests(unittest.TestCase):
    def test_same_cursor_with_more_results_is_stalled(self):
        cursor = {"page": 3, "token": ["a", 1]}
        self.assertTrue(cursor_is_stalled(cursor, {"has_more": True, "next_cursor": cursor.copy()}))

    def test_advanced_or_finished_cursor_is_not_stalled(self):
        self.assertFalse(cursor_is_stalled({"page": 3}, {"has_more": True, "next_cursor": {"page": 4}}))
        self.assertFalse(cursor_is_stalled({"page": 3}, {"has_more": False, "next_cursor": {"page": 3}}))


if __name__ == "__main__":
    unittest.main()
