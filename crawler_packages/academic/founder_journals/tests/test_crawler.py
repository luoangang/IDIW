import gzip
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("founder_journals_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_fixture_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(fields, set(item))

    def test_catalog_is_stable(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(101, len(rows))
        self.assertEqual(len(rows), len({row["journal_key"] for row in rows}))
        self.assertTrue(all(row.get("data_source") == "official_api" for row in rows))

    def test_normalize_current_issue_record(self):
        journal = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn",
                   "base_url": "https://example.cn", "site_id": 1}
        item = crawler.normalize({"id": 123, "resName": "当期文章", "authors": "张三;李四",
                                  "summary": "摘要", "doi": "10.1/test", "year": 2026,
                                  "firstPageNum": 1, "lastPageNum": 10}, journal, {"year": 2026, "issue": 5})
        self.assertEqual("当期文章", item["title"])
        self.assertEqual("2026年第5期", item["issue"])
        self.assertEqual("1-10", item["pages"])
        self.assertEqual("founder", item["source_api"])

    def test_get_json_decompresses_gzip(self):
        payload = json.dumps({"status": 0, "data": {"id": 1}}).encode("utf-8")

        class Response:
            headers = {"Content-Encoding": "gzip"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size):
                return gzip.compress(payload)

        with patch.object(crawler, "urlopen", return_value=Response()):
            self.assertEqual({"id": 1}, crawler.get_json("https://example.cn/api", 10))

    def test_normalize_cleans_markup_and_filters_noise(self):
        journal = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn",
                   "base_url": "https://example.cn", "site_id": 1}
        item = crawler.normalize({"id": 1, "resName": "Ag-Cu-<italic>x</italic>Ti@Sc<sub>2</sub>O<sub>3</sub>",
                                  "year": 2026}, journal, {"year": 2026, "issue": 5})
        self.assertEqual("Ag-Cu-xTi@Sc2O3", item["title"])
        self.assertIsNone(crawler.normalize({"id": 2, "resName": "2026年第5期封面和目录"}, journal,
                                            {"year": 2026, "issue": 5}))
        self.assertIsNone(crawler.normalize({"id": 3, "resName": "先进传感技术与器件专栏"}, journal,
                                            {"year": 2026, "issue": 5}))

    def test_collect_latest_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "base_url": "https://example.cn", "site_id": 1}}
        record = {"id": 123, "resName": "当期文章", "year": 2026}
        request = {"query": "不会匹配", "limit": 1,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 1}}
        with patch.object(crawler, "read_current_issue", return_value=({"year": 2026, "issue": 5}, [record])):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_keyword_filter_matches_current_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "base_url": "https://example.cn", "site_id": 1}}
        records = [{"id": 1, "resName": "人工智能教育研究", "year": 2026},
                   {"id": 2, "resName": "农业经济研究", "year": 2026}]
        request = {"query": "人工智能", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "keywords", "per_journal_limit": 5}}
        with patch.object(crawler, "read_current_issue", return_value=({"year": 2026, "issue": 5}, records)):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual("人工智能教育研究", items[0]["title"])
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
