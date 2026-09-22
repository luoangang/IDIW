import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("candidate_crawler", ROOT / "crawler.py")
CRAWLER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CRAWLER
SPEC.loader.exec_module(CRAWLER)


class CrawlerTests(unittest.TestCase):
    def test_search_sql_contains_keyword_fields_and_page(self):
        value = CRAWLER.search_sql("人工智能", "1", 3)
        self.assertIn("人工智能[Title]", value)
        self.assertIn("人工智能[Abstract]", value)
        self.assertIn("3[Pager]", value)

    def test_parse_magetech_result(self):
        document = '''
        <li id="art123456" class="noselectrow">
          <div class="j-title"><a href="https://www.lis.ac.cn/CN/10.13266/test">人工智能研究</a></div>
          <div class="j-author">张三, 李四</div>
          <span class="j-volumn">2026, 70(1): 1-10</span>
          <div class="j-abstract"><p>这是摘要。</p></div>
          <a href="https://doi.org/10.13266/test">DOI</a>
          <script>lsdy1('PDF','987','https://www.lis.ac.cn')</script>
        </li>
        '''
        item = CRAWLER.parse_items(document, CRAWLER.JOURNALS["lis"])[0]
        self.assertEqual("123456", item["external_id"])
        self.assertEqual(["张三", "李四"], item["authors"])
        self.assertEqual(2026, item["year"])
        self.assertEqual("10.13266/test", item["doi"])
        self.assertIn("id=987", item["pdf_url"])

    def test_fixture_matches_manifest_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(fields, set(item))

    def test_all_three_journals_are_configured(self):
        self.assertEqual({"data_analysis", "lis", "qbzl"}, set(CRAWLER.JOURNALS))


if __name__ == "__main__":
    unittest.main()
