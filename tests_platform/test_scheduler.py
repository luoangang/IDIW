import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore


class ScheduleTimeTests(unittest.TestCase):
    def test_daily_time_uses_beijing_and_crosses_local_midnight(self):
        before = datetime(2026, 10, 14, 0, 59, 59)  # 08:59:59 Beijing
        self.assertEqual(
            datetime(2026, 10, 14, 1, 0),
            PlatformStore._next_run("daily", "09:00", None, after=before),
        )
        self.assertEqual(
            datetime(2026, 10, 15, 1, 0),
            PlatformStore._next_run("daily", "09:00", None,
                                    after=datetime(2026, 10, 14, 1, 0)),
        )
        self.assertEqual(
            datetime(2026, 10, 13, 16, 0),
            PlatformStore._next_run("daily", "00:00", None,
                                    after=datetime(2026, 10, 13, 15, 59)),
        )

    def test_weekly_time_and_bad_inputs(self):
        self.assertEqual(
            datetime(2026, 10, 18, 1, 0),
            PlatformStore._next_run("weekly", "09:00", 7,
                                    after=datetime(2026, 10, 14, 0, 0)),
        )
        for args in (("daily", "25:00", None), ("weekly", "09:00", 0),
                     ("daily", "not-a-time", None)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                PlatformStore._next_run(*args)

    def test_due_slot_is_used_as_stable_dedupe_key(self):
        store = PlatformStore(SETTINGS)
        due = datetime(2026, 10, 14, 1, 0)
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{"id": 12, "next_run_at": due}]
        store.connect = Mock(return_value=connection)
        store.enqueue_monitor = Mock(return_value=37)

        self.assertEqual([37], store.enqueue_due_monitors())
        store.enqueue_monitor.assert_called_once_with(
            12, "scheduled", "schedule:12:2026-10-14T01:00:00", expected_due=due,
        )


class ScheduleApiTests(unittest.TestCase):
    def test_daily_schedule_can_be_set_on_an_existing_monitor(self):
        store = Mock()
        client = create_app(SETTINGS, store).test_client()
        response = client.patch("/api/v1/monitors/9/schedule", json={
            "schedule_type": "daily", "schedule_time": "09:00", "enabled": True,
        })
        self.assertEqual(200, response.status_code)
        store.update_monitor_schedule.assert_called_once_with(9, "daily", "09:00", None, True)


if __name__ == "__main__":
    unittest.main()
