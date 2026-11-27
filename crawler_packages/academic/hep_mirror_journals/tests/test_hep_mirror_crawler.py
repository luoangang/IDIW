import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPEC = importlib.util.spec_from_file_location("hep_mirror_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


PAGE = """<html><body>
<a href="https://cjournal.hep.com.cn/1671-6833/CN/home">首页</a>
<a href="https://cjournal.hep.com.cn/1671-6833/CN/10.13705/j.issn.1671-6833.2026.03.001">考虑道路附着系数的智能车辆主动避撞</a>
<a href="https://cjournal.hep.com.cn/1671-6833/CN/10.13705/j.issn.1671-6833.2026.03.001">摘要</a>
<a href="https://cjournal.hep.com.cn/1673-8268/CN/1271798671067579105">数据要素权利配置中的权利堆叠困境及其破解</a>
<a href="https://cjournal.hep.com.cn/1671-6833/CN/current">当期目录</a>
</body></html>"""


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_item_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(fields, set(item))

    def test_catalog_is_stable(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(6, len(rows))
        self.assertEqual(len(rows), len({row["journal_key"] for row in rows}))
        self.assertTrue(all(row.get("data_source") == "public_mirror" for row in rows))
        self.assertTrue(all("非官网" in row.get("tags", []) for row in rows))

    def test_parse_toc_supports_doi_and_numeric_ids(self):
        items = crawler.parse_toc(PAGE, {
            "journal_key": "a" * 16,
            "name": "示例期刊",
            "url": "https://example.cn",
            "current_url": "https://cjournal.hep.com.cn/1671-6833/CN/current",
        })
        self.assertEqual(2, len(items))
        self.assertEqual("10.13705/j.issn.1671-6833.2026.03.001", items[0]["external_id"])
        self.assertEqual("1271798671067579105", items[1]["external_id"])
        self.assertEqual("hep_mirror", items[0]["source_api"])

    def test_collect_latest_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://cjournal.hep.com.cn/1671-6833/CN/current"}}
        request = {"query": "不会匹配", "limit": 2,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 2,
                                  "enrich_abstract": False}}
        with patch.object(crawler, "read_page", return_value=PAGE):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_keyword_filter_matches_current_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://cjournal.hep.com.cn/1671-6833/CN/current"}}
        request = {"query": "智能车辆", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "keywords", "per_journal_limit": 5}}
        with patch.object(crawler, "read_page", return_value=PAGE):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual("考虑道路附着系数的智能车辆主动避撞", items[0]["title"])
        self.assertEqual([], warnings)

    def test_extract_abstract_prefers_citation_meta(self):
        abstract = crawler.extract_detail_abstract(fixture("detail_citation.html"))
        self.assertIn("容积卡尔曼滤波", abstract)
        self.assertNotIn("过短的站点描述", abstract)
        self.assertGreater(len(abstract), crawler.ABSTRACT_MIN_LENGTH)

    def test_extract_abstract_falls_back_to_description_and_jsonld(self):
        self.assertIn("扩张状态观测器", crawler.extract_detail_abstract(fixture("detail_description.html")))
        self.assertIn("权利堆叠", crawler.extract_detail_abstract(fixture("detail_jsonld.html")))

    def test_extract_abstract_rejects_short_text(self):
        self.assertIsNone(crawler.extract_detail_abstract(fixture("detail_short.html")))

    def test_enrich_fills_only_empty_with_limit(self):
        items = [
            {"url": "https://cjournal.hep.com.cn/1/CN/a", "title": "甲", "abstract": None},
            {"url": "https://cjournal.hep.com.cn/1/CN/b", "title": "乙", "abstract": "已有摘要，不应覆盖"},
            {"url": "https://cjournal.hep.com.cn/1/CN/c", "title": "丙", "abstract": None},
            {"url": "https://cjournal.hep.com.cn/1/CN/d", "title": "丁", "abstract": None},
        ]
        warnings = []
        with patch.object(crawler, "fetch_detail", side_effect=lambda url, timeout: fixture("detail_citation.html")), \
                patch.object(crawler.time, "sleep"):
            attempts = crawler.enrich_abstracts(items, 10, 2, warnings, "示例期刊")
        self.assertEqual(2, attempts)
        self.assertIsNotNone(items[0]["abstract"])
        self.assertEqual("已有摘要，不应覆盖", items[1]["abstract"])
        self.assertIsNotNone(items[2]["abstract"])
        self.assertIsNone(items[3]["abstract"])
        self.assertEqual([], warnings)

    def test_enrich_failure_is_non_fatal(self):
        items = [
            {"url": "https://cjournal.hep.com.cn/1/CN/a", "title": "甲", "abstract": None},
            {"url": "https://cjournal.hep.com.cn/1/CN/b", "title": "乙", "abstract": None},
        ]
        warnings = []
        pages = {"https://cjournal.hep.com.cn/1/CN/a": URLError("timeout"),
                 "https://cjournal.hep.com.cn/1/CN/b": fixture("detail_citation.html")}

        def fake_fetch(url, timeout):
            value = pages[url]
            if isinstance(value, Exception):
                raise value
            return value

        with patch.object(crawler, "fetch_detail", side_effect=fake_fetch), patch.object(crawler.time, "sleep"):
            crawler.enrich_abstracts(items, 10, 4, warnings, "示例期刊")
        self.assertIsNone(items[0]["abstract"])
        self.assertIsNotNone(items[1]["abstract"])
        self.assertEqual(1, len(warnings))
        self.assertIn("摘要补采失败", warnings[0])

    def test_collect_enriches_missing_abstract_in_latest_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://cjournal.hep.com.cn/1671-6833/CN/current"}}
        request = {"query": "不会匹配", "limit": 2,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 2, "abstract_enrich_limit": 1}}
        with patch.object(crawler, "read_page", return_value=PAGE), \
                patch.object(crawler, "fetch_detail", return_value=fixture("detail_citation.html")), \
                patch.object(crawler.time, "sleep"):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertEqual(1, successful)
        self.assertIsNotNone(items[0]["abstract"])
        self.assertIsNone(items[1]["abstract"])
        self.assertEqual([], warnings)

    def test_collect_respects_enrich_switch(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://cjournal.hep.com.cn/1671-6833/CN/current"}}
        request = {"query": "不会匹配", "limit": 2,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 2, "enrich_abstract": False}}
        with patch.object(crawler, "read_page", return_value=PAGE), \
                patch.object(crawler, "fetch_detail") as fetch:
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertIsNone(items[0]["abstract"])
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
