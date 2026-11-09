import json
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch

import pytest

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.weekly_report import (
    generate_summary, previous_week, process_one, validate_summary, week_bounds,
)


EVIDENCE = [{"id": 1, "package_key": "google_news_rss", "title": "具身智能新研究", "summary": "研究摘要"}]
CONTENT = {"overview": "本周出现新研究。", "highlights": [
    {"headline": "研究动态", "detail": "一篇新研究。", "evidence": [1]}], "outlook": "继续观察。"}


def test_week_bounds_use_beijing_and_only_mondays():
    start, end = week_bounds(date(2026, 10, 19))
    assert start.astimezone(timezone.utc) == datetime(2026, 10, 18, 16, tzinfo=timezone.utc)
    assert end - start == timedelta(days=7)
    assert previous_week(date(2026, 10, 28)) == date(2026, 10, 19)
    with pytest.raises(ValueError):
        week_bounds(date(2026, 10, 20))


def test_model_response_is_checked_and_key_not_put_in_body():
    reply = {"model": "deepseek-flash", "usage": {"total_tokens": 18}, "choices": [
        {"finish_reason": "stop", "message": {"content": json.dumps(CONTENT)}}]}
    def opener(request, timeout):
        assert request.get_header("Authorization") == "Bearer secret"
        assert b"secret" not in request.data
        assert timeout == 60
        return BytesIO(json.dumps(reply).encode())
    result = generate_summary("具身智能", date(2026, 10, 19), EVIDENCE, api_key="secret", opener=opener)
    assert result["content"] == CONTENT
    assert result["usage"]["total_tokens"] == 18
    reply["choices"][0]["finish_reason"] = "length"
    with pytest.raises(ValueError, match="incomplete"):
        generate_summary("具身智能", date(2026, 10, 19), EVIDENCE, api_key="secret", opener=opener)
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_summary({**CONTENT, "highlights": [{**CONTENT["highlights"][0], "evidence": [2]}]}, {1})
    assert validate_summary({**CONTENT, "highlights": []}, {1})["highlights"] == []


def test_process_empty_week_does_not_call_model():
    class Store:
        def claim_weekly_report(self):
            return {"id": 4, "monitor_id": 2, "week_start": date(2026, 10, 19),
                    "attempts": 0, "query_text": "具身智能"}
        def weekly_evidence(self, monitor_id, start):
            return 0, []
        def finish_weekly_report(self, report_id, attempt, **data):
            self.finished = (report_id, attempt, data)
        def fail_weekly_report(self, *args):
            raise AssertionError("empty report should not fail")
    store = Store()
    assert process_one(store, generator=lambda *args: (_ for _ in ()).throw(AssertionError("model called")))
    assert store.finished[2]["source_count"] == 0
    assert store.finished[2]["model"] is None


def test_process_failure_is_recorded_for_retry():
    class Store:
        def claim_weekly_report(self):
            return {"id": 4, "monitor_id": 2, "week_start": date(2026, 10, 19),
                    "attempts": 1, "query_text": "具身智能"}
        def weekly_evidence(self, monitor_id, start):
            return 1, EVIDENCE
        def fail_weekly_report(self, report_id, attempt, error):
            self.failure = (report_id, attempt, error)
    store = Store()
    assert process_one(store, generator=lambda *args: (_ for _ in ()).throw(ValueError("bad JSON")))
    assert store.failure == (4, 2, "ValueError: bad JSON")


def test_report_api_requires_key_and_validates_settings():
    class Store:
        def set_weekly_report_enabled(self, monitor_id, enabled):
            self.setting = (monitor_id, enabled)
        def enqueue_weekly_report(self, monitor_id, start):
            self.queued = (monitor_id, start)
            return 5
        def list_weekly_reports(self, monitor_id):
            return []
    store = Store()
    client = create_app(SETTINGS, store).test_client()
    with patch("crawler_platform.api.os.getenv", return_value=None):
        assert client.post("/api/v1/monitors/2/weekly-reports", json={}).status_code == 422
    assert client.patch("/api/v1/monitors/2/weekly-report-settings", json={"enabled": "yes"}).status_code == 422
    assert client.patch("/api/v1/monitors/2/weekly-report-settings", json={"enabled": True}).status_code == 200
    assert store.setting == (2, True)
    with patch("crawler_platform.api.os.getenv", return_value="secret"):
        response = client.post("/api/v1/monitors/2/weekly-reports", json={"week_start": "2026-10-19"})
        assert response.status_code == 202
        assert client.post("/api/v1/monitors/2/weekly-reports", json={"week_start": 123}).status_code == 422
    assert store.queued == (2, date(2026, 10, 19))
