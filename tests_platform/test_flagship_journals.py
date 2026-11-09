import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crawler_platform.protocol import load_manifest, validate_item, validate_parameters


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "crawler_packages" / "academic" / "flagship_journals"
SPEC = importlib.util.spec_from_file_location("flagship_journals_crawler", PACKAGE / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(crawler)


def work(doi="https://doi.org/10.1038/s41586-026-00001-0", abstract=True):
    return {
        "id": "https://openalex.org/W123", "doi": doi,
        "title": "Large language models in research", "publication_date": "2026-01-01",
        "publication_year": 2026,
        "primary_location": {"source": {"issn_l": "0028-0836", "issn": ["0028-0836"]}, "landing_page_url": None},
        "authorships": [{"author": {"display_name": "Jane Doe"}, "institutions": [{"display_name": "Example University"}]}],
        "abstract_inverted_index": {"Large": [0], "language": [1], "models": [2]} if abstract else None,
        "biblio": {"volume": "1", "issue": "2", "first_page": "5", "last_page": "9"},
        "language": "en", "open_access": {"is_oa": True}, "cited_by_count": 4,
    }


def request(**parameters):
    values = validate_parameters(load_manifest(PACKAGE).parameters_schema, parameters)
    return {"execution_id": "00000000-0000-0000-0000-000000000501", "query": "大模型",
            "aliases": ["large language model"], "limit": 10, "parameters": values,
            "time_range": {"from": None, "to": None}}


class FlagshipJournalsTests(unittest.TestCase):
    def test_manifest_and_fixture(self):
        manifest = load_manifest(PACKAGE)
        sample = json.loads((PACKAGE / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(sample["doi"], validate_item(manifest, sample)["doi"])
        self.assertEqual(4, len(validate_parameters(manifest.parameters_schema, {})["journal_keys"]))

    def test_reconstruct_abstract_and_filter_news(self):
        self.assertEqual("Large language models", crawler.abstract_from_index(work()["abstract_inverted_index"]))
        self.assertIsNone(crawler.normalize(work("https://doi.org/10.1038/d41586-026-00001-0"), "nature", ["model"]))
        self.assertIsNone(crawler.normalize(work("https://doi.org/10.1038/s41586-026-00001-0") | {"title": "Correction: models"}, "nature", ["model"]))

    def test_search_dedupe_and_write_protocol(self):
        def fetch(url, timeout):
            self.assertIn("primary_location.source.issn", url)
            self.assertIn("search.title_and_abstract", url)
            self.assertIn("publication_date%3Adesc", url)
            return {"meta": {"count": 2}, "results": [work(), work()]}

        rows, warnings, partial = crawler.collect(request(journal_keys=["nature"]), fetch)
        self.assertEqual(1, len(rows))
        self.assertFalse(partial)
        self.assertEqual([], warnings)
        self.assertEqual(["Jane Doe"], rows[0]["authors"])
        self.assertEqual(["large language model"], rows[0]["matched_terms"])
        validate_item(load_manifest(PACKAGE), rows[0])
        with tempfile.TemporaryDirectory() as directory:
            crawler.write_output(Path(directory), request(), rows, warnings, partial)
            result = json.loads((Path(directory) / "result.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", result["status"])
            self.assertEqual(1, result["item_count"])

    def test_partial_failure_keeps_successful_journal(self):
        def fetch(url, timeout):
            if "0028-0836" in url:
                return {"meta": {"count": 1}, "results": [work()]}
            raise RuntimeError("temporarily unavailable")

        rows, warnings, partial = crawler.collect(request(journal_keys=["nature", "science"]), fetch)
        self.assertEqual(1, len(rows))
        self.assertTrue(partial)
        self.assertIn("science", warnings[0])

    def test_chinese_only_requires_explicit_english_term(self):
        req = request()
        req["aliases"] = []
        with self.assertRaisesRegex(ValueError, "English search term"):
            crawler.collect(req, lambda *_: None)

    def test_missing_abstract_crossref_fallback(self):
        with patch.object(crawler, "get_json", return_value={"message": {"abstract": "<jats:p>A useful abstract.</jats:p>"}}):
            row = crawler.normalize(work(abstract=False), "nature", ["model"])
            crawler.enrich_crossref(row, 5)
        self.assertEqual("A useful abstract.", row["abstract"])
        self.assertEqual("crossref", row["abstract_source"])

    def test_nature_public_abstract_parser_is_bounded_to_abstract(self):
        page = ("<section data-title='Abstract'><div id='Abs1-content'>"
                "<p>Clinical &amp; molecular findings<sup>1</sup> improved outcomes.</p>"
                "<p>Second paragraph.</p></div></section><section><p>Not abstract.</p></section>")
        with patch.object(crawler, "urlopen", return_value=io.BytesIO(page.encode("utf-8"))) as opener:
            abstract = crawler.nature_abstract("10.1038/s41586-026-11328-3", 5)
        self.assertEqual("Clinical & molecular findings improved outcomes. Second paragraph.", abstract)
        self.assertIn("nature.com/articles/s41586-026-11328-3", opener.call_args.args[0].full_url)
        with patch.object(crawler, "urlopen") as opener:
            self.assertIsNone(crawler.nature_abstract("10.1126/science.test", 5))
        opener.assert_not_called()

    def test_nature_fallback_precedes_crossref(self):
        row = crawler.normalize(work(abstract=False), "nature", ["model"])
        with patch.object(crawler, "nature_abstract", return_value="Publisher abstract"):
            crawler.enrich_nature(row, 5)
        self.assertEqual("Publisher abstract", row["abstract"])
        self.assertEqual("nature", row["abstract_source"])


if __name__ == "__main__":
    unittest.main()
