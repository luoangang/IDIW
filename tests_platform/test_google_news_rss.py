import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

from crawler_platform.protocol import load_manifest, validate_item


PACKAGE = Path(__file__).resolve().parents[1] / "crawler_packages" / "news" / "google_news_rss"
SPEC = importlib.util.spec_from_file_location("google_rss_test_crawler", PACKAGE / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(crawler)


def feed(*identities):
    root = ElementTree.Element("rss")
    channel = ElementTree.SubElement(root, "channel")
    for identity in identities:
        item = ElementTree.SubElement(channel, "item")
        for key, value in {"guid": identity, "title": f"Article {identity}",
                           "link": f"https://example.org/{identity}", "description": "<b>Summary</b>",
                           "pubDate": "Sun, 08 Nov 2026 01:00:00 GMT"}.items():
            ElementTree.SubElement(item, key).text = value
        ElementTree.SubElement(item, "source").text = "Example"
    return root


def request(**changes):
    return {"query": "人工智能", "aliases": ["AI for science"], "limit": 10,
            "parameters": {"language": "zh-CN", "country": "CN"}, **changes}


class GoogleRssTests(unittest.TestCase):
    def test_primary_and_aliases_are_normalized_and_deduplicated(self):
        self.assertEqual(["AI", "robotics"], crawler.query_terms(request(
            query=" AI ", aliases=["ai", "ＡＩ", "robotics", " robotics ", ""])))

    def test_aliases_are_fetched_even_if_primary_already_fills_limit(self):
        fetcher = Mock(side_effect=[feed("a", "b", "c"), feed("a", "alias-only")])
        result = crawler.collect(request(limit=2), fetcher)
        self.assertEqual(["人工智能", "AI for science"], [call.args[0] for call in fetcher.call_args_list])
        self.assertEqual(["a", "alias-only"], [row["external_id"] for row in result["items"]])
        self.assertEqual("completed", result["status"])

    def test_duplicates_by_id_or_url_are_not_returned_twice(self):
        first = crawler.parse_items(feed("a", "b"), {})
        second = crawler.parse_items(feed("a", "c"), {})
        second[1]["url"] = first[1]["url"]
        merged = crawler.merge_batches([first, second], 10)
        self.assertEqual(["a", "c"], [row["external_id"] for row in merged])
        self.assertEqual(len(merged), len({row["url"] for row in merged}))

    def test_limit_is_global_not_per_term(self):
        result = crawler.collect(request(aliases=["alpha", "beta"], limit=3),
                                 Mock(side_effect=[feed("a", "b"), feed("c", "d"), feed("e", "f")]))
        self.assertEqual(["a", "c", "e"], [row["external_id"] for row in result["items"]])

    def test_primary_only_preserves_order_and_region(self):
        fetcher = Mock(return_value=feed("a", "b"))
        result = crawler.collect(request(aliases=[], parameters={"language": "en-US", "country": "GB"}), fetcher)
        self.assertEqual(1, fetcher.call_count)
        self.assertEqual(["a", "b"], [row["external_id"] for row in result["items"]])
        self.assertEqual("en-US", result["items"][0]["language"])
        self.assertEqual("GB", result["items"][0]["country"])

    def test_failed_alias_preserves_primary_results(self):
        result = crawler.collect(request(), Mock(side_effect=[feed("a"), TimeoutError("unavailable")]))
        self.assertEqual("partial", result["status"])
        self.assertEqual(1, len(result["items"]))
        self.assertIsNone(result["error"])
        self.assertEqual("AI for science", result["warnings"][0]["query"])

    def test_failed_primary_can_be_recovered_by_alias(self):
        result = crawler.collect(request(), Mock(side_effect=[TimeoutError("unavailable"), feed("alias-only")]))
        self.assertEqual("partial", result["status"])
        self.assertEqual("alias-only", result["items"][0]["external_id"])

    def test_all_failures_have_visible_error_details(self):
        result = crawler.collect(request(), Mock(side_effect=TimeoutError("timed out")))
        self.assertEqual("failed", result["status"])
        self.assertEqual([], result["items"])
        self.assertIn("timed out", result["error"]["message"])

    def test_expired_deadline_makes_no_network_request(self):
        fetcher = Mock()
        result = crawler.collect(request(deadline_at="2000-01-01T00:00:00Z"), fetcher)
        fetcher.assert_not_called()
        self.assertEqual("failed", result["status"])
        self.assertEqual("DEADLINE_APPROACHING", result["warnings"][0]["code"])

    def test_timeout_is_bounded_by_remaining_deadline(self):
        fetcher = Mock(return_value=feed("a"))
        deadline = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
        crawler.collect(request(aliases=[], deadline_at=deadline), fetcher)
        self.assertGreater(fetcher.call_args.args[2], 0)
        self.assertLess(fetcher.call_args.args[2], 8)

    def test_bad_date_does_not_discard_article(self):
        root = feed("a")
        root.find("./channel/item/pubDate").text = "not a date"
        item = crawler.parse_items(root, {})[0]
        self.assertIsNone(item["published_at"])
        self.assertEqual("Summary", item["summary"])
        validate_item(load_manifest(PACKAGE), item)

    def test_url_encodes_exact_search_and_region(self):
        opener = Mock(return_value=io.BytesIO(ElementTree.tostring(feed("a"))))
        with patch.object(crawler, "urlopen", opener):
            crawler.fetch_feed('具身智能 "AI for science"', {"language": "en-US", "country": "GB"}, 7)
        parameters = parse_qs(urlsplit(opener.call_args.args[0].full_url).query)
        self.assertEqual(['具身智能 "AI for science"'], parameters["q"])
        self.assertEqual(["GB:en"], parameters["ceid"])
        self.assertEqual(7, opener.call_args.kwargs["timeout"])

    def test_html_response_is_not_reported_as_empty_success(self):
        with patch.object(crawler, "urlopen", return_value=io.BytesIO(b"<html><body>blocked</body></html>")):
            with self.assertRaisesRegex(ValueError, "not an RSS"):
                crawler.fetch_feed("AI", {}, 5)

    def test_invalid_request_fails_before_network(self):
        for changes in ({"aliases": "not-list"}, {"aliases": [123]}, {"limit": True},
                        {"limit": 0}, {"query": ""}, {"aliases": ["x"] * 31}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                crawler.collect(request(**changes), Mock())

    def test_output_warning_and_item_count_follow_protocol(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            items = crawler.parse_items(feed("a"), {})
            crawler.write_output(output, "test", items, "partial", warnings=[{"code": "QUERY_FAILED", "message": "timeout"}])
            result = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(1, result["item_count"])
            self.assertEqual("partial", result["status"])
            self.assertEqual(1, len((output / "items.jsonl").read_text(encoding="utf-8").splitlines()))


if __name__ == "__main__":
    unittest.main()
