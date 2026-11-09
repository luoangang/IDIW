import json
import unittest
from pathlib import Path

from crawler_platform.protocol import ProtocolError, load_manifest, validate_item, validate_parameters


PACKAGE = Path(__file__).resolve().parents[1] / "crawler_packages" / "news" / "rss_multi_feed"


class RssContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest(PACKAGE)

    def test_defaults_and_output_fixture(self):
        config = validate_parameters(self.manifest.parameters_schema, {})
        self.assertEqual(4, len(config["feed_urls"]))
        self.assertFalse(self.manifest.incremental)
        sample = json.loads((PACKAGE / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        validate_item(self.manifest, sample)

    def test_invalid_feed_and_nested_groups_are_rejected(self):
        for values in ({"feed_urls": []}, {"feed_urls": ["file:///secret"]}, {"keyword_groups": [[123]]}):
            with self.subTest(values=values), self.assertRaises(ProtocolError):
                validate_parameters(self.manifest.parameters_schema, values)

    def test_resource_limits_are_validated(self):
        for values in ({"per_feed_limit": 0}, {"timeout_seconds": 1000}, {"max_feed_bytes": 20000000}):
            with self.subTest(values=values), self.assertRaises(ProtocolError):
                validate_parameters(self.manifest.parameters_schema, values)

    def test_query_specific_data_is_not_stored_in_raw_schema(self):
        names = set(self.manifest.field_map)
        self.assertNotIn("query", names)
        self.assertNotIn("matched_terms", names)

    def test_expanded_deployment_config_matches_existing_protocol(self):
        path = PACKAGE.parents[2] / "configs" / "rss-multi-feed-expanded.json"
        preset = json.loads(path.read_text(encoding="utf-8"))
        config = validate_parameters(self.manifest.parameters_schema, preset)
        urls = config["feed_urls"]
        self.assertEqual(32, len(urls))
        self.assertEqual(len(urls), len(set(urls)))
        original = validate_parameters(self.manifest.parameters_schema, {})["feed_urls"]
        self.assertTrue(set(original).issubset(urls))
        self.assertEqual(1000, config["per_feed_limit"])
        self.assertEqual(0, config["lookback_days"])
        self.assertEqual("keywords", config["match_mode"])
        self.assertFalse(any("sciencedaily.com" in url or "theguardian.com" in url for url in urls))

