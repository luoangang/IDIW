import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("supplement_journals_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_fixture_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(fields, set(item))

    def test_catalog_is_stable_and_resolved(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(338, len(rows))
        self.assertEqual(len(rows), len({row["journal_key"] for row in rows}))
        self.assertTrue(all(row["issns"] for row in rows))
        self.assertTrue(all(row["issn"] in row["issns"] for row in rows))

    def test_catalog_has_source_metadata(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertTrue(all(row.get("source_system") == "openalex_crossref" for row in rows))
        self.assertTrue(all(row.get("status") == "verified" for row in rows))
        self.assertTrue(all(row.get("catalog_source") in {"2377_catalog", "core_2026-11-24"} for row in rows))
        self.assertTrue(all(row.get("data_source") == "openalex_crossref" for row in rows))
        for row in rows:
            self.assertIn("采集:OpenAlex/Crossref", row.get("tags", []))
            self.assertIn("非官网", row.get("tags", []))
            self.assertNotIn("低空核心", row.get("tags", []))
            self.assertFalse(row["journal_key"].startswith("lowalt_"))

    def test_pending_catalog_is_sourced(self):
        rows = json.loads((ROOT / "pending_journals.json").read_text(encoding="utf-8"))
        self.assertEqual(1480, len(rows))
        self.assertTrue(all(row.get("source_system") == "2377_catalog" for row in rows))
        self.assertTrue(all(row.get("status") in {"pending_adapter", "promoted", "blocked"} for row in rows))
        self.assertTrue(all(row.get("source_group") for row in rows))
        for row in rows:
            if row.get("status") == "promoted":
                self.assertIn(
                    row.get("data_source"),
                    {"official_site", "official_api", "official_rss", "official_toc", "public_mirror"},
                )
                self.assertEqual(row.get("data_source"), row.get("planned_data_source"))
            else:
                self.assertEqual(row.get("data_source"), "pending")
                self.assertEqual(row.get("planned_data_source"), "official_site")
        for row in rows:
            if row.get("status") == "pending_adapter":
                self.assertIn("采集:待适配", row.get("tags", []))
                self.assertIn("官网候选", row.get("tags", []))
            self.assertIn("目录:2377", row.get("tags", []))

    def test_abstract_reconstruction(self):
        index = {"Low-altitude": [0], "economy": [1], "review": [2]}
        self.assertEqual("Low-altitude economy review", crawler.abstract_from_index(index))
        self.assertIsNone(crawler.abstract_from_index({}))

    def test_editorial_titles_are_excluded(self):
        row = crawler.JOURNALS["91951a14a7ce0ca5"]
        item = {"DOI": "10.1/editorial", "type": "journal-article", "title": ["Editorial: new issue"]}
        self.assertIsNone(crawler.crossref_record(item, row, "2772-4247", []))

    def test_crossref_record_normalizes_metadata(self):
        row = crawler.JOURNALS["91951a14a7ce0ca5"]
        item = {
            "DOI": "10.1016/j.commtr.2026.1", "type": "journal-article",
            "title": ["<i>Low</i> altitude economy"], "URL": "https://doi.org/10.1016/j.commtr.2026.1",
            "author": [{"given": "Alice", "family": "Zhang", "affiliation": [{"name": "Tsinghua"}]}],
            "published": {"date-parts": [[2026, 10, 1]]},
            "volume": "6", "issue": "1", "page": "1-10", "abstract": "<jats:p>Abstract</jats:p>",
            "is-referenced-by-count": 4, "language": "en",
        }
        record = crawler.crossref_record(item, row, "2772-4247", ["low altitude"])
        self.assertEqual("10.1016/j.commtr.2026.1", record["doi"])
        self.assertEqual(["Alice Zhang"], record["authors"])
        self.assertEqual(["Tsinghua"], record["affiliations"])
        self.assertEqual("2026-10-01", record["published_at"])
        self.assertEqual("Abstract", record["abstract"])
        self.assertEqual("crossref", record["source_api"])
        self.assertEqual(["low altitude"], record["matched_terms"])

    def test_latest_issue_uses_openalex_first(self):
        work = {
            "doi": "https://doi.org/10.1/test", "display_name": "A paper",
            "publication_date": "2026-11-01", "publication_year": 2026,
            "authorships": [], "biblio": {}, "open_access": {"is_oa": True},
            "cited_by_count": 1, "id": "https://openalex.org/W1", "language": "en",
        }
        request = {
            "query": "ignored", "limit": 1, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": ["91951a14a7ce0ca5"], "collect_mode": "latest_issue",
                           "per_journal_limit": 1, "lookback_days": 30},
        }
        with patch.object(crawler, "fetch_openalex", return_value=[work]) as mocked:
            items, warnings, successful = crawler.collect(request)
        self.assertEqual(1, len(items))
        self.assertEqual("openalex", items[0]["source_api"])
        self.assertEqual([], items[0]["matched_terms"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertIn("2772-4247", mocked.call_args.args[0])

    def test_openalex_failure_falls_back_to_crossref(self):
        item = {
            "DOI": "10.1/fallback", "type": "journal-article", "title": ["Low altitude fallback paper"],
            "URL": "https://doi.org/10.1/fallback", "published": {"date-parts": [[2026, 11, 2]]},
        }
        request = {
            "query": "low altitude", "limit": 1, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": ["91951a14a7ce0ca5"], "collect_mode": "keywords",
                           "search_terms": ["low altitude"], "per_journal_limit": 1},
        }
        with patch.object(crawler, "fetch_openalex", side_effect=crawler.SourceUnavailable("429")), \
             patch.object(crawler, "fetch_crossref", return_value=[item]):
            items, warnings, successful = crawler.collect(request)
        self.assertEqual(1, len(items))
        self.assertEqual("crossref", items[0]["source_api"])
        self.assertEqual(["low altitude"], items[0]["matched_terms"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)


if __name__ == "__main__":
    unittest.main()
