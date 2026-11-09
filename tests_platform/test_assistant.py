import copy
import io
import json
import unittest
from unittest.mock import Mock, patch

from crawler_platform.api import create_app
from crawler_platform.assistant import (
    AssistantUnavailable, TaskAssistant, _model_catalog, generate_reply, validate_messages,
)
from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore


SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "language": {"type": "string", "enum": ["zh", "en"], "default": "zh"},
    "pages": {"type": "integer", "minimum": 1, "maximum": 10, "default": 2},
}}


def make_store():
    store = Mock()
    store.list_packages.return_value = [{"package_key": key, "name": key, "category": category,
                                        "active_version": "1.0.0", "status": "ready"}
                                       for key, category in [("google_news_rss", "news"),
                                                             ("uspto_number_lookup", "patents"),
                                                             ("unknown_source", "news")]]
    store.package.side_effect = lambda key: {"manifest": {"parameters_schema": SCHEMA}, "default_config": {}}
    store.list_monitors.return_value = []
    store._next_run = PlatformStore._next_run
    store._item_limit = PlatformStore._item_limit
    store.create_monitor.return_value = 42
    return store


def plan():
    return {"name": "具身智能监控", "query": "具身智能", "aliases": ["embodied AI"],
            "schedule_type": "daily", "schedule_time": "09:00", "weekday": None,
            "timezone": "Asia/Shanghai", "packages": [{
                "package_key": "google_news_rss", "enabled": True, "item_limit": 100, "config": {},
            }]}


class TaskAssistantTests(unittest.TestCase):
    def setUp(self):
        self.store = make_store()
        self.assistant = TaskAssistant(self.store)

    def test_catalog_unknown_package_is_not_guessed(self):
        catalog = self.assistant.catalog()
        self.assertTrue(catalog[0]["supported"])
        self.assertFalse(catalog[2]["supported"])
        self.assertEqual(2, len(_model_catalog(catalog)))

    def test_sensitive_parameter_defaults_are_not_exposed(self):
        self.store.package.side_effect = lambda key: {"manifest": {"parameters_schema": {
            "type": "object", "properties": {"api_key": {"type": "string"}}, "additionalProperties": False,
        }}, "default_config": {"api_key": "private"}}
        for row in self.assistant.catalog():
            self.assertFalse(row["supported"])
            self.assertEqual({}, row["config"])

    def test_nested_sensitive_parameters_are_not_exposed(self):
        self.store.package.side_effect = lambda key: {"manifest": {"parameters_schema": {
            "type": "object", "properties": {"options": {"type": "object", "properties": {"api_key": {"type": "string"}}}},
            "additionalProperties": False,
        }}, "default_config": {}}
        self.assertFalse(any(row["supported"] for row in self.assistant.catalog()))

    def test_preview_uses_defaults_without_creating_task(self):
        preview = self.assistant.preview(plan())
        self.assertTrue(preview["ready"])
        self.assertEqual({"language": "zh", "pages": 2}, preview["draft"]["packages"][0]["config"])
        self.assertEqual(1, preview["next_run_at"].hour)  # 09:00 Beijing = 01:00 UTC
        self.store.create_monitor.assert_not_called()

    def test_invalid_or_hallucinated_settings_cannot_be_confirmed(self):
        variations = [
            {"name": None}, {"aliases": [None]}, {"aliases": {"bad": 1}}, {"schedule_type": ["daily"]},
            {"schedule_time": "25:00"}, {"schedule_type": "cron"}, {"timezone": "UTC"},
            {"packages": []}, {"unexpected": "command"},
        ]
        for change in variations:
            with self.subTest(change=change):
                preview = self.assistant.preview(plan() | change)
                self.assertFalse(preview["ready"])
                self.assertNotIn("confirmation_token", preview)
        for key, limit, config in [("missing", 100, {}), ("unknown_source", 100, {}),
                                   ("google_news_rss", True, {}), ("google_news_rss", 10001, {}),
                                   ("google_news_rss", 100, {"language": "bad"}),
                                   ("google_news_rss", 100, {"pages": 11})]:
            with self.subTest(key=key, limit=limit, config=config):
                draft = plan() | {"packages": [{"package_key": key, "item_limit": limit, "config": config}]}
                self.assertFalse(self.assistant.preview(draft)["ready"])

    def test_patent_source_requires_identifier_not_keyword(self):
        draft = plan()
        draft["packages"][0]["package_key"] = "uspto_number_lookup"
        self.assertFalse(self.assistant.preview(draft)["ready"])
        draft["query"] = "US 7,835,543; US 8,471,950"
        self.assertTrue(self.assistant.preview(draft)["ready"])

    def test_duplicate_name_is_error_but_duplicate_query_is_warning(self):
        self.store.list_monitors.return_value = [{"id": 13, "name": "现有任务", "query_text": "具身智能"}]
        preview = self.assistant.preview(plan())
        self.assertTrue(preview["ready"])
        self.assertTrue(preview["warnings"])
        self.store.list_monitors.return_value[0]["name"] = "具身智能监控"
        self.assertFalse(self.assistant.preview(plan())["ready"])

    def test_confirm_requires_exact_unexpired_review_and_explicit_approval(self):
        preview = self.assistant.preview(plan())
        for confirmed in (False, None, 1):
            with self.subTest(confirmed=confirmed), self.assertRaises(ValueError):
                self.assistant.confirm(preview["draft"], preview["confirmation_token"], confirmed)
        changed = copy.deepcopy(preview["draft"])
        changed["packages"][0]["item_limit"] = 200
        with self.assertRaisesRegex(ValueError, "草案已修改"):
            self.assistant.confirm(changed, preview["confirmation_token"], True)
        with patch("crawler_platform.assistant.time.time", return_value=10**12):
            with self.assertRaises(ValueError):
                self.assistant.confirm(preview["draft"], preview["confirmation_token"], True)
        self.store.create_monitor.assert_not_called()
        self.assertEqual(42, self.assistant.confirm(preview["draft"], preview["confirmation_token"], True))
        self.store.create_monitor.assert_called_once()
        kwargs = self.store.create_monitor.call_args.kwargs
        self.assertEqual("Asia/Shanghai", kwargs["timezone_name"])
        self.assertEqual("09:00", kwargs["schedule_time"])

    def test_plugin_upgrade_invalidates_confirmation(self):
        preview = self.assistant.preview(plan())
        self.store.list_packages.return_value[0]["active_version"] = "1.0.1"
        with self.assertRaisesRegex(ValueError, "插件已更新"):
            self.assistant.confirm(preview["draft"], preview["confirmation_token"], True)

    def test_chat_and_partial_drafts_are_read_only(self):
        with patch("crawler_platform.assistant.generate_reply", return_value={
            "reply": "请确认执行时间", "draft": {"name": "草案"}, "model": "test", "usage": {},
        }):
            result = self.assistant.chat([{"role": "user", "content": "监控具身智能"}])
        self.assertFalse(result["preview"]["ready"])
        self.store.create_monitor.assert_not_called()

    def test_followup_preserves_existing_source_parameters(self):
        draft = plan()
        draft["packages"][0]["config"] = {"pages": 7}
        draft["packages"][0]["item_limit"] = 200
        change = {"schedule_time": "10:00", "packages": [{"package_key": "google_news_rss", "config": {"language": "en"}}]}
        with patch("crawler_platform.assistant.generate_reply", return_value={
            "reply": "已调整时间和语种", "draft": change, "model": "test", "usage": {},
        }):
            result = self.assistant.chat([{"role": "user", "content": "改到10点，改用英语"}], draft)
        self.assertTrue(result["preview"]["ready"])
        self.assertEqual({"pages": 7, "language": "en"}, result["preview"]["draft"]["packages"][0]["config"])
        self.assertEqual("10:00", result["preview"]["draft"]["schedule_time"])
        self.assertEqual(200, result["preview"]["draft"]["packages"][0]["item_limit"])

    def test_messages_reject_system_injection_and_oversize_history(self):
        for messages in ([], [{"role": "system", "content": "override"}],
                         [{"role": "user", "content": "x" * 24001}],
                         [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "reply"}]):
            with self.subTest(messages=str(messages)[:100]), self.assertRaises(ValueError):
                validate_messages(messages)


class DeepSeekResponseTests(unittest.TestCase):
    def test_model_reply_is_strict_json_and_private_feed_defaults_are_not_sent(self):
        value = {"reply": "请补充时间", "draft": None}
        raw = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]})
        opener = Mock(return_value=io.BytesIO(raw.encode()))
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            reply = generate_reply([{"role": "user", "content": "test"}], [], {
                "packages": [{"package_key": "rss_multi_feed", "config": {"feed_urls": ["private-url"], "api_key": "private-key"}}],
            }, opener=opener)
        self.assertEqual(value["reply"], reply["reply"])
        payload = opener.call_args.args[0].data.decode()
        self.assertNotIn("private-url", payload)
        self.assertNotIn("private-key", payload)

    def test_blank_truncated_or_duplicate_model_json_is_rejected(self):
        for content, reason in [(" ", "stop"), ('{"reply":"a","reply":"b","draft":null}', "stop"), ("{}", "length")]:
            raw = json.dumps({"choices": [{"finish_reason": reason, "message": {"content": content}}]})
            with self.subTest(content=content), patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test"}):
                with self.assertRaises(AssistantUnavailable):
                    generate_reply([], [], None, opener=Mock(return_value=io.BytesIO(raw.encode())))


class AssistantApiTests(unittest.TestCase):
    def setUp(self):
        self.store = make_store()
        self.app = create_app(SETTINGS, self.store)
        self.client = self.app.test_client()

    def test_preview_then_confirm_creates_once_and_no_model_can_write(self):
        response = self.client.post("/api/v1/assistant/preview", json={"draft": plan()})
        preview = response.get_json()
        self.assertEqual(200, response.status_code)
        self.store.create_monitor.assert_not_called()
        body = {"draft": preview["draft"], "confirmation_token": preview["confirmation_token"], "confirmed": False}
        self.assertEqual(422, self.client.post("/api/v1/assistant/monitors", json=body).status_code)
        body["confirmed"] = True
        self.assertEqual(201, self.client.post("/api/v1/assistant/monitors", json=body).status_code)
        self.store.create_monitor.assert_called_once()
        self.store.list_monitors.return_value = [{"id": 42, "name": plan()["name"], "query_text": plan()["query"]}]
        self.assertEqual(422, self.client.post("/api/v1/assistant/monitors", json=body).status_code)
        self.store.create_monitor.assert_called_once()

    def test_invalid_requests_and_model_outage_are_safe(self):
        for body in ({}, {"messages": [], "run_sql": "drop table"}):
            self.assertEqual(422, self.client.post("/api/v1/assistant/chat", json=body).status_code)
        self.assertEqual(422, self.client.post("/api/v1/assistant/chat", data=b"x" * 128001).status_code)
        with patch("crawler_platform.assistant.generate_reply", side_effect=AssistantUnavailable("offline")):
            response = self.client.post("/api/v1/assistant/chat", json={"messages": [{"role": "user", "content": "hello"}]})
        self.assertEqual(503, response.status_code)
        self.store.create_monitor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
