import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cnki_cbpt_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(crawler)


class CbptCrawlerTests(unittest.TestCase):
    def test_parses_paper_metadata(self):
        parser = crawler.PaperParser()
        parser.feed('''<div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/ABC_123456"><span>文章标题</span></a></h3><span>张三;李四;</span><p class="highText">文章摘要</p><div class="paperInfo"><span class="publish-info">2024 年 01 期</span></div></div>''')
        self.assertEqual(len(parser.papers), 1)
        self.assertEqual(parser.papers[0]["title"], "文章标题")
        self.assertEqual(parser.papers[0]["authors"], "张三;李四;")
        self.assertEqual(parser.papers[0]["abstract"], "文章摘要")

    def test_collect_uses_catalog_and_handles_partial_failure(self):
        journals = {
            "a" * 16: {"name": "期刊甲", "url": "http://hbsb.cbpt.cnki.net"},
            "b" * 16: {"name": "期刊乙", "url": "http://test.cbpt.cnki.net"},
        }
        def fake_page(base_url, query, page, timeout):
            if "test.cbpt" in base_url:
                raise TimeoutError("unavailable")
            return [{"title": "文章标题", "url": "/portal/journal/portal/client/paper/ABC_123456",
                     "authors": "张三;", "abstract": "摘要", "issue": "2024 年 01 期"}]

        with patch.object(crawler, "read_page", side_effect=fake_page):
            items, warnings, successful = crawler.collect(
                {"query": "人工智能", "limit": 2, "parameters": {
                    "journal_keys": ["a" * 16, "b" * 16], "per_journal_limit": 1}}, journals)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["journal_key"], "a" * 16)
        self.assertEqual(successful, 1)
        self.assertEqual(len(warnings), 1)

    def test_bundled_catalog_is_restricted_to_cbpt(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 509)
        self.assertEqual(len({row["journal_key"] for row in rows}), len(rows))
        self.assertTrue(all(row["template_group"] == "cnki_cbpt" for row in rows))

    def test_legacy_www_host_uses_valid_certificate_hostname(self):
        key = "c" * 16
        journals = {key: {"name": "示例期刊", "url": "http://www.styb.cbpt.cnki.net"}}
        with patch.object(crawler, "read_page", return_value=[]) as mocked:
            _, warnings, successful = crawler.collect(
                {"query": "人工智能", "limit": 1, "parameters": {"journal_keys": [key]}}, journals)
        self.assertEqual(successful, 1)
        self.assertEqual(warnings, [])
        self.assertEqual(mocked.call_args.args[0], "https://styb.cbpt.cnki.net")


if __name__ == "__main__":
    unittest.main()
