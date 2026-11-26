import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPEC = importlib.util.spec_from_file_location("paperonce_journals_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_fixture_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(fields, set(item))

    def test_catalog_is_stable(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(78, len(rows))
        self.assertEqual(len(rows), len({row["journal_key"] for row in rows}))
        self.assertTrue(all(row.get("data_source") in {"official_api", "official_site"} for row in rows))
        self.assertTrue(all(any(tag in {"采集:官网API", "采集:官网目次"} for tag in row.get("tags", [])) for row in rows))

    def test_normalize_current_issue_record(self):
        journal = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        item = crawler.normalize({"ArticleID": 123, "Title": "<b>当期文章</b>", "AuthorsList": "张三,李四",
                                  "Abstract_Chinese": "摘要", "DOI": "10.1/test", "PublishDate": "2026-11-01",
                                  "YearIssue_No": "2026年第5期"}, journal)
        self.assertEqual("当期文章", item["title"])
        self.assertEqual(2026, item["year"])
        self.assertEqual("2026年第5期", item["issue"])
        self.assertEqual("paperonce", item["source_api"])

    def test_normalize_filters_issue_noise(self):
        journal = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        self.assertIsNone(crawler.normalize({"ArticleID": "1", "Title": "202605封面"}, journal))
        self.assertIsNone(crawler.normalize({"ArticleID": "2", "Title": "202605目录"}, journal))

    def test_read_legacy_issue_parses_paperopen_items(self):
        page = '''<div class="item">
        <div class="title"><a href="http://example.cn//oa/darticle.aspx?type=view&id=202606001">真实文章标题</a><span>[1-7]</span></div>
        <div class="authors">张三<sup>a</sup>，李四</div>
        <div class="doi">doi:<a href="http://dx.doi.org/10.3969/test.2026.06.001">10.3969/test.2026.06.001</a></div>
        </div>'''

        class Response:
            headers = {"Content-Type": "text/html; charset=gb2312"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size):
                return page.encode("gb2312")

        with patch.object(crawler, "urlopen", return_value=Response()):
            records = crawler.read_legacy_issue({"url": "http://example.cn"}, 10)
        self.assertEqual(1, len(records))
        self.assertEqual("202606001", records[0]["ArticleID"])
        self.assertEqual("真实文章标题", records[0]["Title"])
        self.assertIn("张三", records[0]["AuthorsList"])
        self.assertIn("李四", records[0]["AuthorsList"])
        self.assertEqual("10.3969/test.2026.06.001", records[0]["DOI"])
        self.assertEqual("2026年第6期", records[0]["YearIssue_No"])
        self.assertIn("/oa/darticle.aspx", records[0]["_url"])

    def test_collect_latest_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn"}}
        record = {"ArticleID": 123, "Title": "当期文章", "AuthorsList": "张三", "PublishDate": "2026-11-01"}
        request = {"query": "不会匹配", "limit": 1,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 1,
                                  "enrich_abstract": False}}
        with patch.object(crawler, "read_current_issue", return_value=[record]):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_keyword_filter_matches_current_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn"}}
        records = [{"ArticleID": 1, "Title": "人工智能教育研究", "PublishDate": "2026-11-01"},
                   {"ArticleID": 2, "Title": "农业经济研究", "PublishDate": "2026-11-01"}]
        request = {"query": "人工智能", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "keywords", "per_journal_limit": 5}}
        with patch.object(crawler, "read_current_issue", return_value=records):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual("人工智能教育研究", items[0]["title"])
        self.assertEqual([], warnings)

    def test_extract_abstract_from_lbzy(self):
        abstract = crawler.extract_detail_abstract(fixture("detail_lbzy.html"))
        self.assertIn("供应链协同", abstract)
        self.assertNotIn("关键词", abstract)

    def test_extract_abstract_falls_back_to_inline(self):
        abstract = crawler.extract_detail_abstract(fixture("detail_inline.html"))
        self.assertIn("组织联结", abstract)
        self.assertNotIn("契约治理机制的政策建议。 关键词", abstract)

    def test_extract_abstract_supports_english_inline(self):
        abstract = crawler.extract_detail_abstract(fixture("detail_english.html"))
        self.assertIn("urban renewal programmes", abstract)
        self.assertTrue(abstract.startswith("This paper"))
        self.assertNotIn("Keywords", abstract)

    def test_read_detail_retries_once_on_502(self):
        calls = []

        def fake_fetch(url, timeout):
            calls.append(url)
            if len(calls) == 1:
                raise HTTPError(url, 502, "Bad Gateway", {}, None)
            return fixture("detail_lbzy.html")

        with patch.object(crawler, "fetch_detail", side_effect=fake_fetch), \
                patch.object(crawler.time, "sleep") as sleep:
            page = crawler.read_detail("http://example.cn//oa/darticle.aspx?type=view&id=202606001", 10)
        self.assertIn("LbZY", page)
        self.assertEqual(2, len(calls))
        sleep.assert_called_once_with(crawler.RETRY_DELAY)

    def test_read_detail_does_not_retry_other_errors(self):
        with patch.object(crawler, "fetch_detail", side_effect=HTTPError("http://x", 500, "err", {}, None)), \
                patch.object(crawler.time, "sleep") as sleep:
            with self.assertRaises(HTTPError):
                crawler.read_detail("http://x/oa/darticle.aspx?id=1", 10)
        sleep.assert_not_called()

    def test_enrich_fills_only_empty_and_keeps_double_slash_url(self):
        url = "http://xdjyyxzz.paperopen.com//oa/darticle.aspx?type=view&id=202606001"
        items = [
            {"url": url, "title": "甲", "abstract": None},
            {"url": url + "2", "title": "乙", "abstract": "已有中文摘要，不应覆盖"},
            {"url": "https://example.cn/#/digest?ArticleID=3", "title": "丙", "abstract": None},
        ]
        warnings = []
        with patch.object(crawler, "read_detail", return_value=fixture("detail_lbzy.html")) as read, \
                patch.object(crawler.time, "sleep"):
            attempts = crawler.enrich_abstracts(items, 10, 5, warnings, "示例期刊")
        self.assertEqual(1, attempts)
        self.assertIsNotNone(items[0]["abstract"])
        self.assertEqual("已有中文摘要，不应覆盖", items[1]["abstract"])
        self.assertIsNone(items[2]["abstract"])
        self.assertEqual(url, read.call_args[0][0])
        self.assertEqual([], warnings)

    def test_enrich_failure_is_non_fatal_and_respects_limit(self):
        items = [{"url": f"http://example.cn/oa/darticle.aspx?id={index}", "title": "文章", "abstract": None}
                 for index in range(5)]
        warnings = []
        with patch.object(crawler, "read_detail", side_effect=OSError("connection reset")), \
                patch.object(crawler.time, "sleep") as sleep:
            attempts = crawler.enrich_abstracts(items, 10, 2, warnings, "示例期刊")
        self.assertEqual(2, attempts)
        self.assertEqual(2, len(warnings))
        self.assertTrue(all("摘要补采失败" in warning for warning in warnings))
        self.assertTrue(all(item["abstract"] is None for item in items))
        self.assertEqual(2, sleep.call_count)

    def test_collect_enriches_legacy_items(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn"}}
        records = [{"ArticleID": "202606001", "Title": "有摘要的文章",
                    "Abstract_Chinese": "已有摘要", "_url": "http://example.cn//oa/darticle.aspx?id=1"},
                   {"ArticleID": "202606002", "Title": "缺摘要的文章",
                    "_url": "http://example.cn//oa/darticle.aspx?id=2"}]
        request = {"query": "不会匹配", "limit": 2,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 2, "abstract_enrich_limit": 1}}
        with patch.object(crawler, "read_current_issue", return_value=records), \
                patch.object(crawler, "read_detail", return_value=fixture("detail_lbzy.html")), \
                patch.object(crawler.time, "sleep"):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertEqual(1, successful)
        self.assertEqual("已有摘要", items[0]["abstract"])
        self.assertIsNotNone(items[1]["abstract"])
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
