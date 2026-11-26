import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("oa_rss_journals_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<title>示例期刊</title><year>2026</year><month>11</month><day>20</day>
<item>
  <title>《示例期刊》2026年第10期目录</title>
  <link>/tyb/oa/darticle.aspx?type=view&amp;id=202610000</link>
  <description>目录</description>
</item>
<item>
  <title><![CDATA[<b>当期文章</b>]]></title>
  <link>/tyb/oa/darticle.aspx?type=view&amp;id=202601001</link>
  <description><![CDATA[摘要<br/>第二行]]></description>
  <author>张三,李四</author>
  <issue>2026年10</issue>
  <pubDate>2026年10月20日</pubDate>
</item>
</channel></rss>
"""


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_item_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        item = crawler.parse_feed(RSS.encode("utf-8"), {
            "journal_key": "a" * 16,
            "name": "示例期刊",
            "url": "https://example.cn/tyb",
        })[0]
        self.assertEqual(fields, set(item))

    def test_catalog_is_stable(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(18, len(rows))
        self.assertEqual(len(rows), len({row["journal_key"] for row in rows}))
        self.assertTrue(all(row.get("data_source") == "official_rss" for row in rows))
        self.assertTrue(all("采集:官网RSS" in row.get("tags", []) for row in rows))

    def test_parse_rss_filters_directory_and_resolves_relative_link(self):
        items = crawler.parse_feed(RSS.encode("utf-8"), {
            "journal_key": "a" * 16,
            "name": "示例期刊",
            "url": "https://example.cn/tyb",
        })
        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual("当期文章", item["title"])
        self.assertEqual("https://example.cn/tyb/oa/darticle.aspx?type=view&id=202601001", item["url"])
        self.assertEqual("202601001", item["external_id"])
        self.assertEqual("张三,李四", item["authors"])
        self.assertEqual("摘要 第二行", item["abstract"])
        self.assertEqual(2026, item["year"])
        self.assertEqual("2026年10", item["issue"])
        self.assertEqual("oa_rss", item["source_api"])

    def test_collect_latest_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn/tyb"}}
        request = {
            "query": "不会匹配",
            "limit": 1,
            "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 1},
        }
        with patch.object(crawler, "read_feed", return_value=RSS.encode("utf-8")):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_keyword_filter_matches_current_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn/tyb"}}
        request = {"query": "当期", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "keywords", "per_journal_limit": 5}}
        with patch.object(crawler, "read_feed", return_value=RSS.encode("utf-8")):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual("当期文章", items[0]["title"])
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
