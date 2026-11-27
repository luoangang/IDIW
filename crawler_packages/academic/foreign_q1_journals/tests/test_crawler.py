import csv
import importlib.util
import json
import re
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("foreign_q1_journals_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)

WATCHLIST = ROOT.parents[2] / "journal_catalog" / "foreign" / "foreign_journals_q1_2026-11-25.csv"
JOURNAL_KEY = "10f85e4f8b86e557"
ISSN = "1615-4150"
ISSN_RE = re.compile(r"^[0-9]{4}-[0-9]{3}[0-9X]$")


def load_journals():
    return json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))


def bulk_journal(key, issns):
    return {"journal_key": key, "name": f"Journal {key}", "issn": issns[0], "issns": issns}


def bulk_work(doi, title, issns, abstract=None):
    work = {
        "id": f"https://openalex.org/{doi}",
        "doi": f"https://doi.org/{doi}",
        "title": title,
        "publication_date": "2026-11-10",
        "publication_year": 2026,
        "type": "article",
        "authorships": [],
        "biblio": {},
        "primary_location": {"source": {"issn": issns, "issn_l": issns[0]}},
        "open_access": {"is_oa": False},
        "cited_by_count": 0,
        "language": "en",
    }
    if abstract:
        work["abstract_inverted_index"] = abstract
    return work


def bulk_request(keys, **parameters):
    values = {
        "journal_keys": keys,
        "collect_mode": "bulk_window",
        "per_journal_limit": 5,
        "lookback_days": 30,
    }
    values.update(parameters)
    return {
        "query": "", "limit": 1000, "aliases": [],
        "deadline_at": "2099-01-01T00:00:00Z",
        "parameters": values,
    }


def query_of(url):
    return parse_qs(urlsplit(url).query)


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_fixture_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(fields, set(item))

    def test_catalog_count_and_identity(self):
        rows = load_journals()
        self.assertEqual(5238, len(rows))
        self.assertEqual(len(rows), len({row["journal_key"] for row in rows}))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{16}", row["journal_key"]) for row in rows))

    def test_catalog_rows_have_required_fields(self):
        rows = load_journals()
        required = {
            "journal_key", "name", "name_en", "issn", "issns", "publisher", "url", "tags",
            "jcr_quartile", "primary_category", "scopus_active", "scopus_top_levels",
        }
        for row in rows:
            self.assertTrue(required <= set(row), row["journal_key"])
            self.assertTrue(row["name"].strip())
            self.assertEqual(row["name"], row["name_en"])
            self.assertIsInstance(row["publisher"], str)
            self.assertIsInstance(row["url"], str)
            self.assertEqual("Q1", row["jcr_quartile"])
            self.assertTrue(row["issns"], row["journal_key"])
            self.assertEqual(len(row["issns"]), len(set(row["issns"])))
            self.assertIn(row["issn"], row["issns"])
            self.assertTrue(all(ISSN_RE.fullmatch(value) for value in row["issns"]))
            self.assertIn(row["scopus_active"], {"Active", "Unknown"})

    def test_catalog_tags_cover_q1_scope(self):
        for row in load_journals():
            tags = row["tags"]
            self.assertEqual(4, len(tags), row["journal_key"])
            self.assertEqual("JCR:Q1", tags[0])
            self.assertEqual("EDITION:" + (row["edition"] or "?"), tags[1])
            self.assertRegex(
                tags[2],
                r"^频次:(年刊|半年刊|季刊|双月刊|月刊|半月刊|周刊|每年[0-9]+期|未知)$",
            )
            self.assertEqual((row["primary_category"] or "").strip()[:24], tags[3])
            self.assertFalse(any(tag.startswith("SCOPUS:") for tag in tags))

    # 2026-11-25 watchlist（5,279 行，含 41 本 Inactive）频次分布：
    # annual 758、semiannual 160、triannual 148、quarterly 1,371、5/year 85、
    # bimonthly 920、10ish 332、monthly 1,161、semimonthly 200、weekly 43、unknown 101。
    # 其中 33 本 JCR 未给 PUBLICATION FREQUENCY（缺失）；68 本为 13–17 期/年，
    # 不落在任何命名区间，按规则记为 unknown，但保留 issues_per_year 与“每年 N 期”标签。
    # 包内仅 include_daily=yes 的 5,238 本：annual 751、semiannual 159、triannual 146、
    # quarterly 1,358、5/year 85、bimonthly 910、10ish 332、monthly 1,154、
    # semimonthly 200、weekly 43、unknown 100。
    def test_catalog_frequency_columns(self):
        def expected_class(issues):
            if issues >= 40:
                return "weekly"
            if 18 <= issues <= 36:
                return "semimonthly"
            if issues == 12:
                return "monthly"
            if 7 <= issues <= 11:
                return "10ish"
            if issues == 6:
                return "bimonthly"
            if issues == 5:
                return "5/year"
            if issues == 4:
                return "quarterly"
            if issues == 3:
                return "triannual"
            if issues == 2:
                return "semiannual"
            if issues == 1:
                return "annual"
            return "unknown"

        allowed = {
            "weekly", "semimonthly", "monthly", "10ish", "bimonthly", "5/year",
            "quarterly", "triannual", "semiannual", "annual", "unknown",
        }
        for row in load_journals():
            publication_frequency = row["publication_frequency"]
            issues = row["issues_per_year"]
            self.assertIsInstance(publication_frequency, str)
            self.assertIn(row["frequency_class"], allowed, row["journal_key"])
            if issues is None:
                self.assertEqual("", publication_frequency)
                self.assertEqual("unknown", row["frequency_class"])
                continue
            self.assertIsInstance(issues, int)
            self.assertEqual(issues, int(publication_frequency.split()[0]))
            self.assertRegex(publication_frequency, r"^[0-9]+ issues?/year$")
            self.assertEqual(expected_class(issues), row["frequency_class"])

    @unittest.skipUnless(WATCHLIST.is_file(), "watchlist CSV 不在当前工作区")
    def test_watchlist_has_frequency_columns(self):
        with WATCHLIST.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            index = fields.index("edition")
            self.assertEqual(
                ["publication_frequency", "issues_per_year", "frequency_class"],
                fields[index + 1:index + 4],
            )
            watchlist = {
                row["journal_id"].strip(): row
                for row in reader
                if (row.get("include_daily") or "").strip().lower() == "yes"
            }
        catalog = load_journals()
        self.assertEqual(len(catalog), len(watchlist))
        self.assertEqual(49, len(fields))  # 原 46 列 + 3 个频次列
        for row in catalog:
            source = watchlist[row["journal_key"]]
            self.assertEqual(source["publication_frequency"], row["publication_frequency"])
            expected_issues = source["issues_per_year"]
            self.assertEqual(
                int(expected_issues) if expected_issues else None,
                row["issues_per_year"],
            )
            self.assertEqual(source["frequency_class"], row["frequency_class"])

    @unittest.skipUnless(WATCHLIST.is_file(), "watchlist CSV 不在当前工作区")
    def test_catalog_matches_watchlist_include_daily(self):
        with WATCHLIST.open(encoding="utf-8-sig", newline="") as handle:
            expected = {
                row["journal_id"].strip()
                for row in csv.DictReader(handle)
                if (row.get("include_daily") or "").strip().lower() == "yes"
            }
            handle.seek(0)
            excluded = {
                row["journal_id"].strip()
                for row in csv.DictReader(handle)
                if (row.get("include_daily") or "").strip().lower() == "no"
            }
        keys = {row["journal_key"] for row in load_journals()}
        self.assertEqual(expected, keys)
        self.assertFalse(keys & excluded)

    def test_catalog_size_within_platform_limit(self):
        self.assertLessEqual((ROOT / "journals.json").stat().st_size, 4_000_000)

    def test_manifest_parameters(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("foreign_q1_journals", manifest["package_key"])
        self.assertEqual("1.1.1", manifest["package_version"])
        self.assertEqual("国外 Q1 期刊包", manifest["name"])
        self.assertIn("OpenAlex", manifest["description"])
        self.assertIn("Crossref", manifest["description"])
        properties = manifest["parameters_schema"]["properties"]
        rows = load_journals()
        keys = properties["journal_keys"]
        self.assertEqual(len(rows), keys["maxItems"])
        self.assertEqual(20, len(keys["default"]))
        self.assertEqual(len(keys["default"]), len(set(keys["default"])))
        catalog_keys = {row["journal_key"] for row in rows}
        self.assertTrue(set(keys["default"]) <= catalog_keys)
        self.assertEqual(
            ["keywords", "latest_issue", "bulk_window"],
            properties["collect_mode"]["enum"],
        )
        self.assertEqual(100, properties["bulk_size"]["default"])
        self.assertEqual(1, properties["bulk_size"]["minimum"])
        self.assertEqual(100, properties["bulk_size"]["maximum"])
        self.assertEqual(30, properties["lookback_days"]["default"])
        self.assertEqual(1, properties["lookback_days"]["minimum"])
        self.assertEqual(90, properties["lookback_days"]["maximum"])
        self.assertEqual(20, properties["per_journal_limit"]["default"])
        self.assertEqual(1, properties["per_journal_limit"]["minimum"])
        self.assertEqual(100, properties["per_journal_limit"]["maximum"])
        self.assertEqual(25, properties["timeout_seconds"]["default"])
        self.assertEqual(5, properties["timeout_seconds"]["minimum"])
        self.assertEqual(120, properties["timeout_seconds"]["maximum"])
        self.assertFalse(properties["require_abstract"]["default"])
        self.assertEqual([], properties["search_terms"]["default"])
        self.assertEqual(["doi"], manifest["output_schema"]["identity_fields"])

    def test_crawler_defaults_match_manifest(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        defaults = manifest["parameters_schema"]["properties"]["journal_keys"]["default"]
        self.assertEqual(defaults, crawler.DEFAULT_KEYS)
        self.assertTrue(set(crawler.DEFAULT_KEYS) <= set(crawler.JOURNALS))
        self.assertEqual("IDIW-ForeignQ1Journals/1.0 (public metadata)", crawler.USER_AGENT)

    def test_abstract_reconstruction(self):
        index = {"Low-altitude": [0], "economy": [1], "review": [2]}
        self.assertEqual("Low-altitude economy review", crawler.abstract_from_index(index))
        self.assertIsNone(crawler.abstract_from_index({}))

    def test_editorial_titles_are_excluded(self):
        row = crawler.JOURNALS[JOURNAL_KEY]
        item = {"DOI": "10.1/editorial", "type": "journal-article", "title": ["Editorial: new issue"]}
        self.assertIsNone(crawler.crossref_record(item, row, ISSN, []))

    def test_crossref_record_normalizes_metadata(self):
        row = crawler.JOURNALS[JOURNAL_KEY]
        item = {
            "DOI": "10.1002/adsc.2026.1", "type": "journal-article",
            "title": ["<i>Practical</i> heterocycle synthesis"], "URL": "https://doi.org/10.1002/adsc.2026.1",
            "author": [{"given": "Alice", "family": "Zhang", "affiliation": [{"name": "Tsinghua"}]}],
            "published": {"date-parts": [[2026, 11, 10]]},
            "volume": "368", "issue": "22", "page": "4100-4110", "abstract": "<jats:p>Abstract</jats:p>",
            "is-referenced-by-count": 4, "language": "en",
        }
        record = crawler.crossref_record(item, row, ISSN, ["heterocycle"])
        self.assertEqual("10.1002/adsc.2026.1", record["doi"])
        self.assertEqual(["Alice Zhang"], record["authors"])
        self.assertEqual(["Tsinghua"], record["affiliations"])
        self.assertEqual("2026-11-10", record["published_at"])
        self.assertEqual("Abstract", record["abstract"])
        self.assertEqual("crossref", record["source_api"])
        self.assertEqual(["heterocycle"], record["matched_terms"])

    def test_latest_issue_uses_openalex_first(self):
        work = {
            "doi": "https://doi.org/10.1/test", "display_name": "A paper",
            "publication_date": "2026-11-10", "publication_year": 2026,
            "authorships": [], "biblio": {}, "open_access": {"is_oa": True},
            "cited_by_count": 1, "id": "https://openalex.org/W1", "language": "en",
        }
        request = {
            "query": "ignored", "limit": 5, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": [JOURNAL_KEY], "collect_mode": "latest_issue",
                           "per_journal_limit": 5, "lookback_days": 14},
        }
        with patch.object(crawler, "fetch_openalex", return_value=[work]) as mocked:
            items, warnings, successful = crawler.collect(request)
        self.assertEqual(1, len(items))
        self.assertEqual("openalex", items[0]["source_api"])
        self.assertEqual([], items[0]["matched_terms"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(ISSN, mocked.call_args.args[0])

    def test_openalex_failure_falls_back_to_crossref(self):
        item = {
            "DOI": "10.1/fallback", "type": "journal-article", "title": ["Heterocycle fallback paper"],
            "URL": "https://doi.org/10.1/fallback", "published": {"date-parts": [[2026, 11, 2]]},
        }
        request = {
            "query": "heterocycle", "limit": 5, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": [JOURNAL_KEY], "collect_mode": "keywords",
                           "search_terms": ["heterocycle"], "per_journal_limit": 5},
        }
        with patch.object(crawler, "fetch_openalex", side_effect=crawler.SourceUnavailable("429")), \
             patch.object(crawler, "fetch_crossref", return_value=[item]):
            items, warnings, successful = crawler.collect(request)
        self.assertEqual(1, len(items))
        self.assertEqual("crossref", items[0]["source_api"])
        self.assertEqual(["heterocycle"], items[0]["matched_terms"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_openalex_empty_results_fall_back_to_crossref(self):
        item = {
            "DOI": "10.1/empty-openalex", "type": "journal-article", "title": ["Empty OpenAlex heterocycle fallback paper"],
            "URL": "https://doi.org/10.1/empty-openalex", "published": {"date-parts": [[2026, 11, 6]]},
        }
        request = {
            "query": "heterocycle", "limit": 5, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": [JOURNAL_KEY], "collect_mode": "keywords",
                           "search_terms": ["heterocycle"], "per_journal_limit": 5},
        }
        with patch.object(crawler, "fetch_openalex", return_value=[]) as openalex_mock, \
             patch.object(crawler, "fetch_crossref", return_value=[item]) as crossref_mock:
            items, warnings, successful = crawler.collect(request)
        self.assertEqual(1, len(items))
        self.assertEqual("crossref", items[0]["source_api"])
        self.assertEqual(["heterocycle"], items[0]["matched_terms"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertTrue(openalex_mock.called)
        self.assertEqual(ISSN, crossref_mock.call_args.args[0])

    def test_openalex_filtered_records_fall_back_to_crossref(self):
        # OpenAlex 返回 1 条但没有 DOI（会被 openalex_record 过滤）：
        # 1.0.2 的空结果回退必须照常触发；Crossref 也空时不得静默计为成功。
        filtered = {"display_name": "Editorial: special issue", "publication_date": "2026-11-05"}
        request = {
            "query": "heterocycle", "limit": 5, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": [JOURNAL_KEY], "collect_mode": "keywords",
                           "search_terms": ["heterocycle"], "per_journal_limit": 5},
        }
        with patch.object(crawler, "fetch_openalex", return_value=[filtered]) as openalex_mock, \
             patch.object(crawler, "fetch_crossref", return_value=[]) as crossref_mock:
            items, warnings, successful = crawler.collect(request)
        self.assertTrue(openalex_mock.called)
        self.assertEqual(ISSN, crossref_mock.call_args_list[0].args[0])
        self.assertEqual([], items)
        self.assertEqual(0, successful)
        self.assertEqual(["JOURNAL_ITEMS_FILTERED"], [warning["code"] for warning in warnings])

    def test_crossref_filtered_records_are_not_counted_as_success(self):
        # OpenAlex 空 → Crossref 只返回编辑类记录：同样 0 条，但必须留 warning 且不算成功。
        editorial = {"DOI": "10.1/editorial-only", "type": "journal-article",
                     "title": ["Editorial: new issue"]}
        request = {
            "query": "", "limit": 5, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": [JOURNAL_KEY], "collect_mode": "latest_issue",
                           "per_journal_limit": 5},
        }
        with patch.object(crawler, "fetch_openalex", return_value=[]), \
             patch.object(crawler, "fetch_crossref", return_value=[editorial]):
            items, warnings, successful = crawler.collect(request)
        self.assertEqual([], items)
        self.assertEqual(0, successful)
        self.assertEqual(["JOURNAL_ITEMS_FILTERED"], [warning["code"] for warning in warnings])

    def test_genuinely_empty_sources_still_count_as_answered(self):
        # 两个源都 200 且 0 条（年刊窗口内无新文章）仍算已响应，保持 0 条但不报错。
        request = {
            "query": "", "limit": 5, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": [JOURNAL_KEY], "collect_mode": "latest_issue",
                           "per_journal_limit": 5},
        }
        with patch.object(crawler, "fetch_openalex", return_value=[]), \
             patch.object(crawler, "fetch_crossref", return_value=[]):
            items, warnings, successful = crawler.collect(request)
        self.assertEqual([], items)
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_openalex_results_do_not_trigger_crossref(self):
        work = {
            "doi": "https://doi.org/10.1/no-crossref", "display_name": "OpenAlex only paper",
            "publication_date": "2026-11-12", "publication_year": 2026,
            "authorships": [], "biblio": {}, "cited_by_count": 2,
        }
        request = {
            "query": "heterocycle", "limit": 5, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": [JOURNAL_KEY], "collect_mode": "keywords",
                           "search_terms": ["heterocycle"], "per_journal_limit": 5},
        }
        with patch.object(crawler, "fetch_openalex", return_value=[work]), \
             patch.object(crawler, "fetch_crossref") as crossref_mock:
            items, warnings, successful = crawler.collect(request)
        self.assertEqual(1, len(items))
        self.assertEqual("openalex", items[0]["source_api"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        crossref_mock.assert_not_called()

    def test_collect_uses_configured_defaults(self):
        work = {
            "doi": "https://doi.org/10.1/defaults", "display_name": "Default window paper",
            "publication_date": "2026-11-10", "publication_year": 2026,
            "authorships": [], "biblio": {}, "cited_by_count": 0,
        }
        request = {
            "query": "", "limit": 100, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {"journal_keys": [JOURNAL_KEY], "collect_mode": "latest_issue"},
        }
        with patch.object(crawler, "fetch_openalex", return_value=[work]) as mocked:
            items, _, successful = crawler.collect(request)
        self.assertEqual(1, len(items))
        self.assertEqual(1, successful)
        # fetch_openalex(issn, terms, mode, start, end, limit, timeout)
        _, _, _, start, end, limit, timeout = mocked.call_args.args
        self.assertEqual(20, limit)
        self.assertEqual(25, timeout)
        self.assertEqual(30, (date.fromisoformat(end) - date.fromisoformat(start)).days)

    def test_bulk_groups_100_issns_per_request(self):
        journals = {
            f"bulk{index:03d}": bulk_journal(f"bulk{index:03d}", [f"1000-{index:04d}"])
            for index in range(100)
        }
        request = bulk_request(list(journals))
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json", return_value={
                 "results": [], "meta": {"next_cursor": None},
             }) as mocked:
            items, warnings, successful = crawler.collect(request)
        self.assertEqual([], items)
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(1, mocked.call_count)
        query = query_of(mocked.call_args.args[0])
        self.assertEqual("100", query["per-page"][0])
        self.assertEqual(crawler.BULK_SELECT, query["select"][0])
        self.assertEqual("*", query["cursor"][0])
        group = query["filter"][0].split(",")[0].split(":", 1)[1]
        self.assertEqual(100, len(group.split("|")))

    def test_bulk_size_parameter_controls_grouping(self):
        journals = {
            f"bulk{index:03d}": bulk_journal(f"bulk{index:03d}", [f"1000-{index:04d}"])
            for index in range(100)
        }
        request = bulk_request(list(journals), bulk_size=50)
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json", return_value={
                 "results": [], "meta": {"next_cursor": None},
             }) as mocked:
            items, warnings, successful = crawler.collect(request)
        self.assertEqual([], items)
        self.assertEqual([], warnings)
        self.assertEqual(2, successful)
        self.assertEqual(2, mocked.call_count)
        for call in mocked.call_args_list:
            group = query_of(call.args[0])["filter"][0].split(",")[0].split(":", 1)[1]
            self.assertEqual(50, len(group.split("|")))

    def test_bulk_maps_works_to_journals(self):
        journals = {
            "journal_a": bulk_journal("journal_a", ["1111-1111", "1111-1112"]),
            "journal_b": bulk_journal("journal_b", ["2222-2222"]),
        }
        works = [
            bulk_work("10.1/bulk-a", "Bulk paper A", ["1111-1111"]),
            bulk_work("10.1/bulk-b", "Bulk paper B", ["2222-2222"]),
        ]
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json", return_value={
                 "results": works, "meta": {"next_cursor": None},
             }), \
             patch.object(crawler, "fetch_openalex") as openalex_mock, \
             patch.object(crawler, "fetch_crossref") as crossref_mock:
            items, warnings, successful = crawler.collect(bulk_request(list(journals)))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(2, len(items))
        self.assertEqual({"journal_a": "1111-1111", "journal_b": "2222-2222"},
                         {item["journal_key"]: item["issn"] for item in items})
        self.assertEqual({"openalex"}, {item["source_api"] for item in items})
        self.assertEqual({"10.1/bulk-a", "10.1/bulk-b"}, {item["doi"] for item in items})
        openalex_mock.assert_not_called()
        crossref_mock.assert_not_called()

    def test_bulk_cursor_pagination(self):
        journals = {"journal_a": bulk_journal("journal_a", ["1111-1111"])}
        pages = [
            {"results": [bulk_work("10.1/bulk-1", "Bulk page one", ["1111-1111"])],
             "meta": {"next_cursor": "cursor-2"}},
            {"results": [bulk_work("10.1/bulk-2", "Bulk page two", ["1111-1111"])],
             "meta": {"next_cursor": None}},
        ]
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json", side_effect=pages) as mocked, \
             patch.object(crawler.time, "sleep"):
            items, warnings, successful = crawler.collect(bulk_request(list(journals)))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(2, len(items))
        self.assertEqual(2, mocked.call_count)
        self.assertEqual("*", query_of(mocked.call_args_list[0].args[0])["cursor"][0])
        self.assertEqual("cursor-2", query_of(mocked.call_args_list[1].args[0])["cursor"][0])

    def test_bulk_deduplicates_doi_and_caps_per_journal(self):
        journals = {"journal_a": bulk_journal("journal_a", ["1111-1111"])}
        works = [
            bulk_work("10.1/bulk-a", "Bulk paper A", ["1111-1111"]),
            bulk_work("10.1/bulk-a", "Bulk paper A duplicate", ["1111-1111"]),
            bulk_work("10.1/bulk-b", "Bulk paper B", ["1111-1111"]),
            bulk_work("10.1/bulk-c", "Bulk paper C", ["1111-1111"]),
        ]
        request = bulk_request(list(journals), per_journal_limit=2)
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json", return_value={
                 "results": works, "meta": {"next_cursor": "next"},
             }) as mocked:
            items, warnings, successful = crawler.collect(request)
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(2, len(items))
        self.assertEqual({"10.1/bulk-a", "10.1/bulk-b"}, {item["doi"] for item in items})
        self.assertEqual(1, mocked.call_count)

    def test_bulk_respects_total_limit(self):
        journals = {
            "journal_a": bulk_journal("journal_a", ["1111-1111"]),
            "journal_b": bulk_journal("journal_b", ["2222-2222"]),
        }
        request = bulk_request(list(journals), bulk_size=1)
        request["limit"] = 1
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json", side_effect=[
                 {"results": [bulk_work("10.1/bulk-a", "Bulk paper A", ["1111-1111"])],
                  "meta": {"next_cursor": None}},
                 {"results": [bulk_work("10.1/bulk-b", "Bulk paper B", ["2222-2222"])],
                  "meta": {"next_cursor": None}},
             ]) as mocked:
            items, warnings, successful = crawler.collect(request)
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(1, len(items))
        self.assertEqual("journal_a", items[0]["journal_key"])
        self.assertEqual(1, mocked.call_count)

    def test_bulk_skips_unmatched_issn_work(self):
        journals = {"journal_a": bulk_journal("journal_a", ["1111-1111"])}
        works = [
            bulk_work("10.1/bulk-a", "Bulk paper A", ["1111-1111"]),
            bulk_work("10.1/bulk-x", "Bulk paper elsewhere", ["9999-9999"]),
        ]
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json", return_value={
                 "results": works, "meta": {"next_cursor": None},
             }):
            items, warnings, successful = crawler.collect(bulk_request(list(journals)))
        self.assertEqual(1, successful)
        self.assertEqual(1, len(items))
        self.assertEqual("10.1/bulk-a", items[0]["doi"])
        self.assertEqual(["BULK_UNMATCHED_WORK"], [warning["code"] for warning in warnings])

    def test_bulk_group_failure_does_not_fail_package(self):
        journals = {
            "journal_a": bulk_journal("journal_a", ["1111-1111"]),
            "journal_b": bulk_journal("journal_b", ["2222-2222"]),
        }
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json_retry", side_effect=[
                 crawler.SourceUnavailable("HTTP 503"),
                 {"results": [bulk_work("10.1/bulk-b", "Bulk paper B", ["2222-2222"])],
                  "meta": {"next_cursor": None}},
             ]):
            items, warnings, successful = crawler.collect(
                bulk_request(list(journals), bulk_size=1)
            )
        self.assertEqual(1, successful)
        self.assertEqual(1, len(items))
        self.assertEqual("journal_b", items[0]["journal_key"])
        self.assertEqual(["BULK_GROUP_FAILED"], [warning["code"] for warning in warnings])
        self.assertNotIn("api_key", warnings[0]["message"])

    def test_bulk_retries_source_unavailable(self):
        journals = {"journal_a": bulk_journal("journal_a", ["1111-1111"])}
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json", side_effect=[
                 crawler.SourceUnavailable("HTTP 429"),
                 {"results": [bulk_work("10.1/bulk-a", "Bulk paper A", ["1111-1111"])],
                  "meta": {"next_cursor": None}},
             ]) as mocked, \
             patch.object(crawler.time, "sleep"):
            items, warnings, successful = crawler.collect(bulk_request(list(journals)))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(1, len(items))
        self.assertEqual(2, mocked.call_count)

    def test_bulk_require_abstract(self):
        journals = {"journal_a": bulk_journal("journal_a", ["1111-1111"])}
        works = [
            bulk_work("10.1/bulk-no-abstract", "Bulk paper without abstract", ["1111-1111"]),
            bulk_work("10.1/bulk-abstract", "Bulk paper with abstract", ["1111-1111"],
                      abstract={"Bulk": [0], "abstract": [1], "text": [2]}),
        ]
        request = bulk_request(list(journals), require_abstract=True)
        with patch.dict(crawler.JOURNALS, journals, clear=True), \
             patch.object(crawler, "request_json", return_value={
                 "results": works, "meta": {"next_cursor": None},
             }):
            items, warnings, successful = crawler.collect(request)
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(1, len(items))
        self.assertEqual("10.1/bulk-abstract", items[0]["doi"])
        self.assertEqual("Bulk abstract text", items[0]["abstract"])


if __name__ == "__main__":
    unittest.main()
