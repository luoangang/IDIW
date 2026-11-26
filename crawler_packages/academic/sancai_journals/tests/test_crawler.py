import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sancai_journals_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_fixture_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(fields, set(item))

    def test_collect_latest_issue_ignores_query(self):
        key = "7371a30d9aa7945b"
        journals = {key: {"journal_key": key, "name": "合肥师范学院学报", "url": "https://xbbjb.hfnu.edu.cn"}}
        record = {"ArticleID": 1065, "Title": "当期文章", "AuthorsList": "张三",
                  "Abstract_Chinese": "摘要", "DOI": "10.1/test", "PublishDate": "2026-11-01"}
        request = {"query": "不会匹配", "limit": 1,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 1}}
        with patch.object(crawler, "read_current_issue", return_value=[record]) as mocked:
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual("当期文章", items[0]["title"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual("https://xbbjb.hfnu.edu.cn", mocked.call_args.args[0]["url"])

    def test_manifest_exposes_collect_mode(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        mode = manifest["parameters_schema"]["properties"]["collect_mode"]
        self.assertEqual(["keywords", "latest_issue"], mode["enum"])
        self.assertEqual("keywords", mode["default"])


if __name__ == "__main__":
    unittest.main()
