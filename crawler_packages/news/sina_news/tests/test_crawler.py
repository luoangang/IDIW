import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sina_news_crawler", ROOT / "crawler.py")
CRAWLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CRAWLER)


SAMPLE_ROW = {
    "author": "",
    "ctime": 1790673631,
    "dataTime": "2026-09-29 17:20:31",
    "dataid": "comos:nitnwnf2854413",
    "docType": "news",
    "intro": "2026年9月下旬，中美关系再次升温。",
    "media_show": "经济观察报",
    "searchSummary": "2026年9月下旬，中美关系再次升温。",
    "thumb": "https://n.sinaimg.cn/example.jpg",
    "title": "<font color='red'>中美</font>关系升温",
    "url": "https://finance.sina.com.cn/example.shtml?from=pcsearch",
}


class SinaNewsCrawlerTests(unittest.TestCase):
    def test_convert_item_cleans_html_and_tracking_url(self):
        item = CRAWLER.convert_item(SAMPLE_ROW)
        self.assertEqual("中美关系升温", item["title"])
        self.assertEqual("https://finance.sina.com.cn/example.shtml", item["url"])
        self.assertEqual("2026-09-29T09:20:31Z", item["published_at"])
        self.assertEqual("comos:nitnwnf2854413", item["external_id"])

    @patch.object(CRAWLER, "fetch_page")
    def test_collect_respects_limit_and_returns_offset_cursor(self, fetch_page):
        fetch_page.return_value = [SAMPLE_ROW, {**SAMPLE_ROW, "dataid": "comos:second"}]
        request = json.loads((ROOT / "tests" / "request.json").read_text(encoding="utf-8"))
        items, cursor, has_more, warnings = CRAWLER.collect(request)
        self.assertEqual(1, len(items))
        self.assertEqual({"page": 1, "offset": 1, "page_size": 10}, cursor)
        self.assertTrue(has_more)
        self.assertEqual([], warnings)

    @patch.object(CRAWLER, "fetch_page")
    def test_main_writes_protocol_files(self, fetch_page):
        fetch_page.return_value = [SAMPLE_ROW, {**SAMPLE_ROW, "dataid": "comos:second"}]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            with patch("sys.argv", ["crawler.py", "--request", str(ROOT / "tests" / "request.json"), "--output", str(output)]):
                self.assertEqual(0, CRAWLER.main())
            result = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", result["status"])
            self.assertEqual(1, result["item_count"])
            self.assertEqual(1, len((output / "items.jsonl").read_text(encoding="utf-8").splitlines()))


if __name__ == "__main__":
    unittest.main()
