import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sciengine_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "issue_sample.json").read_text(encoding="utf-8"))
EXPECTED_FIELDS = {
    "journal_key", "journal_name", "journal_url", "external_id", "title", "url",
    "authors", "abstract", "doi", "year", "issue", "volume", "pages",
    "source_api", "pdf_url",
}


class CrawlerTests(unittest.TestCase):
    def test_catalog_has_14_unique_journals(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(14, len(rows))
        self.assertEqual(14, len({row["journal_key"] for row in rows}))
        self.assertEqual(14, len({row["current_url"] for row in rows}))
        self.assertEqual(14, len({row["json_api"] for row in rows}))

        required = {
            "journal_key", "name", "url", "official_url", "current_url", "json_api",
            "latest_issue_api", "article_api_template", "core_levels", "categories", "source_note",
        }
        for row in rows:
            self.assertTrue(required <= set(row), row.get("name"))
            self.assertTrue(row["core_levels"])
            self.assertTrue(row["categories"])
            self.assertIn("sciengine.com", row["current_url"])
            self.assertIn("selectArticlesInJournalOfVolumeAndIssue", row["json_api"])
            self.assertIn("getJournalLatestVolumeAndIssue", row["latest_issue_api"])
            self.assertIn("{volume}", row["article_api_template"])
            self.assertIn("{code}", row["article_api_template"])
            expected_key = hashlib.sha1(
                f"{row['name']}|{row['current_url']}".encode("utf-8")
            ).hexdigest()[:16]
            self.assertEqual(expected_key, row["journal_key"])

        names = [row["name"] for row in rows]
        self.assertNotIn("新型炭材料(中英文)(曾用名:新型炭材料)", names)
        self.assertNotIn("燃料化学学报(中英文)(曾用名:燃料化学学报)", names)
        self.assertEqual(1, sum(1 for row in rows if row["fla"] == "NCM"))
        self.assertEqual(1, sum(1 for row in rows if row["fla"] == "JFCT"))
        ncm = next(row for row in rows if row["fla"] == "NCM")
        jfct = next(row for row in rows if row["fla"] == "JFCT")
        self.assertIn("新型炭材料(中英文)(曾用名:新型炭材料)", ncm["name_aliases"])
        self.assertIn("燃料化学学报(中英文)(曾用名:燃料化学学报)", jfct["name_aliases"])

    def test_manifest_matches_catalog_and_output_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual("sciengine_journals", manifest["package_key"])
        self.assertEqual("1.0.1", manifest["package_version"])
        params = manifest["parameters_schema"]["properties"]
        self.assertEqual(14, params["journal_keys"]["maxItems"])
        self.assertEqual({"latest_issue"}, set(params["collect_mode"]["enum"]))
        self.assertIs(True, params["follow_latest"]["default"])
        self.assertEqual(
            {row["journal_key"] for row in rows},
            set(params["journal_keys"]["default"]),
        )
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(EXPECTED_FIELDS, fields)
        self.assertEqual(2, len(FIXTURE["data"]))
        self.assertTrue(all(field["nullable"] for field in manifest["output_schema"]["fields"]
                            if field["name"] in {"authors", "abstract", "year", "issue", "volume", "pages", "pdf_url"}))

    def test_parse_articles_maps_fields_and_cleans_markup(self):
        journal = crawler.JOURNALS["a2a415ad37482923"]
        items = crawler.parse_articles(FIXTURE, journal)
        self.assertEqual(2, len(items))

        first = items[0]
        self.assertEqual("2005–2020年千烟洲人工林系统内外气象数据集", first["title"])
        self.assertEqual("吕云, 曾文静", first["authors"])
        self.assertEqual("本数据集记录千烟洲人工林气象观测数据 & 质量控制说明。", first["abstract"])
        self.assertEqual("10.11922/11-6035.nesdc.2025.0187.zh", first["doi"])
        self.assertEqual("10.11922/11-6035.nesdc.2025.0187.zh", first["external_id"])
        self.assertEqual("https://www.sciengine.com/doi/10.11922/11-6035.nesdc.2025.0187.zh", first["url"])
        self.assertEqual(2026, first["year"])
        self.assertEqual("11", first["volume"])
        self.assertEqual("3", first["issue"])
        self.assertEqual("1-8", first["pages"])
        self.assertEqual("sciengine", first["source_api"])
        self.assertEqual("https://www.sciengine.com/2096-2223/test-article.pdf", first["pdf_url"])
        self.assertEqual("中国科学数据中英文网络版", first["journal_name"])

        second = items[1]
        self.assertEqual("面向COx协同脱除的催化机理", second["title"])
        self.assertEqual("张三, Li Si", second["authors"])
        self.assertEqual("研究 <CO> 氧化与 & 表面调控。", second["abstract"])
        self.assertEqual("https://www.sciengine.com/doi/10.1016/S1872-5813(26)60712-8", second["url"])
        self.assertEqual("1001-1012", second["pages"])
        self.assertEqual("https://www.sciengine.com/files/test-review.pdf", second["pdf_url"])

    def test_parse_articles_skips_front_matter_missing_doi_and_duplicates(self):
        journal = crawler.JOURNALS["a2a415ad37482923"]
        items = crawler.parse_articles(FIXTURE, journal)
        titles = [item["title"] for item in items]
        self.assertEqual(2, len(items))
        self.assertNotIn("《某专题》卷首语", titles)
        self.assertNotIn("无 DOI 的目次条目", titles)
        self.assertNotIn("重复 DOI 的条目", titles)

    def test_parse_articles_rejects_failed_payload(self):
        journal = crawler.JOURNALS["a2a415ad37482923"]
        with self.assertRaises(ValueError):
            crawler.parse_articles({"success": False, "message": "denied"}, journal)
        with self.assertRaises(ValueError):
            crawler.parse_articles({"success": True, "data": None}, journal)

    def test_collect_follows_new_latest_issue(self):
        journal = crawler.JOURNALS["a2a415ad37482923"]
        calls = []

        def fake_fetch(url, timeout):
            calls.append(url)
            if "getJournalLatestVolumeAndIssue" in url:
                return {"success": True, "data": {"latestVolume": "12", "latestIssue": "4"}}
            if "volume=12" in url and "code=4" in url:
                return FIXTURE
            raise AssertionError(f"unexpected URL: {url}")

        with patch.object(crawler, "fetch_json", side_effect=fake_fetch):
            items, warnings, successful = crawler.collect({
                "limit": 10,
                "parameters": {"journal_keys": [journal["journal_key"]]},
            })
        self.assertEqual(1, successful)
        self.assertEqual(2, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(2, len(calls))
        self.assertIn("getJournalLatestVolumeAndIssue", calls[0])
        self.assertIn("volume=12", calls[1])
        self.assertIn("code=4", calls[1])

    def test_collect_falls_back_when_latest_issue_has_no_articles(self):
        journal = crawler.JOURNALS["a2a415ad37482923"]
        calls = []

        def fake_fetch(url, timeout):
            calls.append(url)
            if "getJournalLatestVolumeAndIssue" in url:
                return {"success": True, "data": {"latestVolume": "99", "latestIssue": "9"}}
            if "volume=99" in url:
                return {"success": True, "data": []}
            return FIXTURE

        with patch.object(crawler, "fetch_json", side_effect=fake_fetch):
            items, warnings, successful = crawler.collect({
                "limit": 10,
                "parameters": {"journal_keys": [journal["journal_key"]]},
            })
        self.assertEqual(1, successful)
        self.assertEqual(2, len(items))
        self.assertEqual(1, len(warnings))
        self.assertIn("最新期无有效文章", warnings[0])
        self.assertEqual(3, len(calls))

    def test_collect_latest_discovery_failure_falls_back_with_one_warning(self):
        journal = crawler.JOURNALS["a2a415ad37482923"]
        calls = []

        def fake_fetch(url, timeout):
            calls.append(url)
            if "getJournalLatestVolumeAndIssue" in url:
                raise crawler.SourceUnavailable("HTTP 503")
            return FIXTURE

        with patch.object(crawler, "fetch_json", side_effect=fake_fetch):
            items, warnings, successful = crawler.collect({
                "limit": 10,
                "parameters": {"journal_keys": [journal["journal_key"]]},
            })
        self.assertEqual(1, successful)
        self.assertEqual(2, len(items))
        self.assertEqual(1, len(warnings))
        self.assertIn("最新期发现失败", warnings[0])
        self.assertIn("HTTP 503", warnings[0])
        self.assertEqual(journal["json_api"], calls[1])

    def test_collect_can_disable_follow_latest(self):
        journal = crawler.JOURNALS["a2a415ad37482923"]
        calls = []
        with patch.object(crawler, "fetch_json", side_effect=lambda url, timeout: calls.append(url) or FIXTURE):
            items, warnings, successful = crawler.collect({
                "limit": 10,
                "parameters": {"journal_keys": [journal["journal_key"]], "follow_latest": False},
            })
        self.assertEqual(1, successful)
        self.assertEqual(2, len(items))
        self.assertEqual([], warnings)
        self.assertEqual([journal["json_api"]], calls)

    def test_collect_unknown_journal_is_non_fatal(self):
        journal = crawler.JOURNALS["a2a415ad37482923"]
        with patch.object(crawler, "fetch_json", return_value=FIXTURE):
            items, warnings, successful = crawler.collect({
                "limit": 10,
                "parameters": {"journal_keys": [journal["journal_key"], "missing"]},
            })
        self.assertEqual(1, successful)
        self.assertEqual(["未知期刊：missing"], warnings)
        self.assertEqual(2, len(items))

    def test_collect_journal_failure_is_non_fatal(self):
        first = crawler.JOURNALS["a2a415ad37482923"]
        second = crawler.JOURNALS["8b235c89e71721e7"]

        def fake_fetch(url, timeout):
            if first["journal_base_id"] in url:
                raise crawler.SourceUnavailable("HTTP 503")
            return FIXTURE

        with patch.object(crawler, "fetch_json", side_effect=fake_fetch):
            items, warnings, successful = crawler.collect({
                "limit": 10,
                "parameters": {"journal_keys": [first["journal_key"], second["journal_key"]]},
            })
        self.assertEqual(1, successful)
        self.assertEqual(2, len(items))
        self.assertEqual(1, len(warnings))
        self.assertIn(first["name"], warnings[0])
        self.assertIn("HTTP 503", warnings[0])

    def test_collect_respects_limit_and_per_journal_limit(self):
        first = crawler.JOURNALS["a2a415ad37482923"]
        second = crawler.JOURNALS["8b235c89e71721e7"]
        keys = [first["journal_key"], second["journal_key"]]
        with patch.object(crawler, "fetch_json", return_value=FIXTURE):
            items, _, _ = crawler.collect({"limit": 1, "parameters": {"journal_keys": keys}})
            self.assertEqual(1, len(items))
            items, _, _ = crawler.collect({
                "limit": 10,
                "parameters": {"journal_keys": keys, "per_journal_limit": 1},
            })
            self.assertEqual(2, len(items))

    def test_collect_rejects_unsupported_mode(self):
        with self.assertRaises(ValueError):
            crawler.collect({
                "limit": 10,
                "parameters": {"collect_mode": "keywords", "journal_keys": ["a" * 16]},
            })
        with self.assertRaises(ValueError):
            crawler.collect({"limit": 10, "parameters": {"journal_keys": []}})


if __name__ == "__main__":
    unittest.main()
