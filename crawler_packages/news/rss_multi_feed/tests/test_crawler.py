import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import feedparser


PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rss_multi_feed_crawler", PACKAGE / "crawler.py")
crawler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawler)


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Example news</title><link>https://example.org/</link>
<language>en</language><description>Test only</description>
<item><title>Embodied AI robot</title><link>https://example.org/robot?utm_source=feed</link>
<description><![CDATA[<p>A humanoid robot uses AI.</p><script>hidden()</script>]]></description>
<author>Research team</author><pubDate>Tue, 13 Oct 2026 09:00:00 GMT</pubDate></item>
<item><title>Military autonomous agents</title><link>https://example.org/defense</link>
<description>Defense researchers test autonomous agents.</description>
<pubDate>Mon, 12 Oct 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom example</title>
<link href="https://example.org/"/><id>urn:feed:example</id><updated>2026-10-13T00:00:00Z</updated>
<entry><title>Robot research</title><id>urn:entry:1</id><link href="https://example.org/atom"/>
<updated>2026-10-13T03:00:00+02:00</updated><content type="html">Robot AI research</content>
</entry></feed>"""


def request(**parameters):
    return {
        "execution_id": "test-rss-execution", "query": "robot", "aliases": [], "limit": 200,
        "parameters": {"feed_urls": ["https://one.example/feed"], **parameters},
        "time_range": {"from": None, "to": None},
    }


def rss_fetcher(url, timeout, max_bytes):
    return feedparser.parse(RSS.encode("utf-8"))


class RssCrawlerTests(unittest.TestCase):
    def test_rss_metadata_and_html_are_normalized(self):
        items, outcome = crawler.collect(request(), rss_fetcher)
        self.assertEqual("completed", outcome["status"])
        self.assertEqual(1, len(items))
        self.assertEqual("https://example.org/robot", items[0]["url"])
        self.assertEqual("2026-10-13T09:00:00Z", items[0]["published_at"])
        self.assertIsNone(items[0]["updated_at"])
        self.assertNotIn("<", items[0]["summary"])
        self.assertNotIn("hidden", items[0]["summary"])
        self.assertEqual("feed_summary", items[0]["content_scope"])

    def test_atom_updated_is_not_mislabeled_as_publication(self):
        items, _ = crawler.collect(request(), lambda *args: feedparser.parse(ATOM))
        self.assertIsNone(items[0]["published_at"])
        self.assertEqual("2026-10-13T01:00:00Z", items[0]["updated_at"])
        self.assertEqual("feed_content", items[0]["content_scope"])

    def test_chinese_query_and_english_aliases(self):
        data = request()
        data.update(query="\u5177\u8eab\u667a\u80fd", aliases=["EMBODIED-AI"])
        items, _ = crawler.collect(data, rss_fetcher)
        self.assertEqual(1, len(items))

    def test_english_keyword_does_not_match_inside_a_word(self):
        self.assertFalse(crawler.contains_term(crawler.normalize("chair fair airplane"), "AI"))
        self.assertTrue(crawler.contains_term(crawler.normalize("AI-powered robotics"), "AI"))

    def test_groups_require_all_terms_and_are_or_combined(self):
        data = request(keyword_groups=[["autonomous", "defense"]])
        data["query"] = "no-match"
        items, _ = crawler.collect(data, rss_fetcher)
        self.assertEqual("Military autonomous agents", items[0]["title"])
        data["parameters"]["keyword_groups"] = [["autonomous", "humanoid"]]
        self.assertEqual([], crawler.collect(data, rss_fetcher)[0])

    def test_all_mode_ignores_keywords(self):
        data = request(match_mode="all")
        data["query"] = "no-match"
        self.assertEqual(2, len(crawler.collect(data, rss_fetcher)[0]))

    def test_no_match_is_success_not_failure(self):
        data = request()
        data["query"] = "no-match"
        items, outcome = crawler.collect(data, rss_fetcher)
        self.assertEqual([], items)
        self.assertEqual("completed", outcome["status"])

    def test_identical_article_across_feeds_is_returned_once(self):
        data = request(feed_urls=["https://one.example/feed", "https://two.example/feed"])
        items, _ = crawler.collect(data, rss_fetcher)
        self.assertEqual(1, len(items))

    def test_identity_and_content_are_independent_of_topic(self):
        first = crawler.collect(request(), rss_fetcher)[0][0]
        second = crawler.collect(request(extra_keywords=["humanoid"]), rss_fetcher)[0][0]
        self.assertEqual(first, second)
        self.assertNotIn("matched_terms", first)

    def test_single_feed_failure_keeps_good_data(self):
        def fetch(url, *args):
            if "two" in url:
                raise crawler.CrawlerError("HTTP_ERROR", "HTTP 503", True)
            return rss_fetcher(url, *args)
        data = request(feed_urls=["https://one.example/feed", "https://two.example/feed"])
        items, outcome = crawler.collect(data, fetch)
        self.assertEqual(1, len(items))
        self.assertEqual("partial", outcome["status"])
        self.assertIsNone(outcome["error"])
        self.assertTrue(any(row["code"] == "FEED_FAILED" for row in outcome["warnings"]))

    def test_all_failed_reports_retryability(self):
        def fetch(*args):
            raise crawler.CrawlerError("NETWORK_ERROR", "offline", True)
        items, outcome = crawler.collect(request(), fetch)
        self.assertEqual([], items)
        self.assertEqual("failed", outcome["status"])
        self.assertTrue(outcome["error"]["retryable"])

    def test_date_range_is_half_open(self):
        data = request(match_mode="all")
        data["time_range"] = {"from": "2026-10-12T09:00:00Z", "to": "2026-10-13T09:00:00Z"}
        items, _ = crawler.collect(data, rss_fetcher)
        self.assertEqual(["Military autonomous agents"], [item["title"] for item in items])

    def test_unknown_dates_are_kept_and_disclosed(self):
        feed = RSS.replace("<pubDate>Tue, 13 Oct 2026 09:00:00 GMT</pubDate>", "")
        data = request()
        data["time_range"]["from"] = "2026-10-13T00:00:00Z"
        items, outcome = crawler.collect(data, lambda *args: feedparser.parse(feed))
        self.assertEqual(1, len(items))
        self.assertTrue(any(row["code"] == "UNKNOWN_DATE" for row in outcome["warnings"]))

    def test_per_feed_limit_is_disclosed(self):
        items, outcome = crawler.collect(request(match_mode="all", per_feed_limit=1), rss_fetcher)
        self.assertEqual(1, len(items))
        self.assertEqual("partial", outcome["status"])
        self.assertTrue(any(row["code"] == "PER_FEED_LIMIT" for row in outcome["warnings"]))

    def test_total_limit_interleaves_sources(self):
        def fetch(url, *args):
            return feedparser.parse(RSS.replace("example.org", url.split("/")[2]))
        data = request(match_mode="all", feed_urls=["https://one.example/feed", "https://two.example/feed"])
        data["limit"] = 2
        items, outcome = crawler.collect(data, fetch)
        self.assertEqual({"one.example", "two.example"}, {item["source_site"] for item in items})
        self.assertEqual("partial", outcome["status"])

    def test_second_poll_returns_new_head_entry_not_old_cursor(self):
        first = crawler.collect(request(), rss_fetcher)[0]
        changed = RSS.replace("<item>", "<item><title>New robot</title><link>https://example.org/new</link></item><item>", 1)
        data = request()
        data["cursor"] = {"page": 20}
        second = crawler.collect(data, lambda *args: feedparser.parse(changed))[0]
        self.assertEqual(1, len(first))
        self.assertEqual(2, len(second))
        self.assertIn("New robot", [item["title"] for item in second])

    def test_invalid_entries_do_not_discard_good_entries(self):
        broken = RSS.replace("<item>", "<item><title>Missing URL</title></item><item>", 1)
        items, outcome = crawler.collect(request(), lambda *args: feedparser.parse(broken))
        self.assertEqual(1, len(items))
        self.assertTrue(any(row["code"] == "ITEMS_SKIPPED" for row in outcome["warnings"]))

    def test_recoverable_feed_parse_issue_is_disclosed(self):
        parsed = feedparser.parse(RSS)
        parsed["bozo"] = True
        items, outcome = crawler.collect(request(), lambda *args: parsed)
        self.assertEqual(1, len(items))
        self.assertTrue(any(row["code"] == "FEED_PARSE_WARNING" for row in outcome["warnings"]))

    def test_expired_deadline_does_not_fetch(self):
        data = request()
        data["deadline_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        with patch.object(crawler, "fetch_feed") as fetch:
            items, outcome = crawler.collect(data)
        fetch.assert_not_called()
        self.assertEqual("failed", outcome["status"])
        self.assertEqual("DEADLINE_EXCEEDED", outcome["error"]["code"])

    def test_url_normalization_preserves_business_parameters(self):
        self.assertEqual("https://example.org/?id=1", crawler.canonical_url("https://EXAMPLE.org/?utm_source=x&id=1#top"))
        self.assertNotEqual(crawler.canonical_url("https://example.org/?id=1"), crawler.canonical_url("https://example.org/?id=2"))

    def test_empty_valid_feed_is_success(self):
        parsed = feedparser.parse('<rss version="2.0"><channel><title>Empty</title></channel></rss>')
        items, outcome = crawler.collect(request(), lambda *args: parsed)
        self.assertEqual([], items)
        self.assertEqual("completed", outcome["status"])

    def test_entrypoint_writes_protocol_files_and_success_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            request_path.write_text(json.dumps(request()), encoding="utf-8")
            output = root / "output"
            with patch.object(sys, "argv", ["crawler.py", "--request", str(request_path), "--output", str(output)]), patch.object(crawler, "fetch_feed", side_effect=rss_fetcher):
                self.assertEqual(0, crawler.main())
            result = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(1, result["item_count"])
            self.assertFalse(result["has_more"])
            self.assertIsNone(result["next_cursor"])
            self.assertEqual(1, len((output / "items.jsonl").read_text(encoding="utf-8").splitlines()))


if __name__ == "__main__":
    unittest.main()
