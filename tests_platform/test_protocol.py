import json
import tempfile
import unittest
from pathlib import Path

from crawler_platform.protocol import ProtocolError, identity_digest, load_manifest, strict_json_loads, validate_item, validate_parameters, validate_upgrade
from crawler_platform.categories import discover_packages


ROOT = Path(__file__).resolve().parents[1]


class ProtocolTests(unittest.TestCase):
    def test_three_example_packages_and_fixtures_conform(self):
        found = []
        for package_dir in discover_packages(ROOT / "crawler_packages"):
            manifest = load_manifest(package_dir)
            sample = json.loads((package_dir / "tests" / "items.jsonl").read_text(encoding="utf-8").splitlines()[0])
            validated = validate_item(manifest, sample)
            self.assertEqual(32, len(identity_digest(manifest, validated)))
            found.append(manifest.package_key)
        self.assertTrue({"baidu_baike", "google_news_rss", "wikipedia"}.issubset(found))
        self.assertEqual(len(found), len(set(found)))

    def test_parameter_defaults_and_unknown_parameter(self):
        manifest = load_manifest(ROOT / "crawler_packages" / "reference" / "wikipedia")
        self.assertEqual({"english_fallback": True}, validate_parameters(manifest.parameters_schema, {}))
        with self.assertRaises(ProtocolError):
            validate_parameters(manifest.parameters_schema, {"unknown": True})

    def test_missing_identity_is_rejected(self):
        manifest = load_manifest(ROOT / "crawler_packages" / "reference" / "baidu_baike")
        sample = json.loads((ROOT / "crawler_packages" / "reference" / "baidu_baike" / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        sample.pop("external_id")
        with self.assertRaises(ProtocolError):
            validate_item(manifest, sample)

    def test_upgrade_keeps_identity_and_existing_fields(self):
        manifest = load_manifest(ROOT / "crawler_packages" / "reference" / "baidu_baike")
        validate_upgrade(manifest, manifest)

    def test_duplicate_json_keys_are_rejected_at_any_depth(self):
        with self.assertRaisesRegex(ProtocolError, "duplicate key: title"):
            strict_json_loads('{"item":{"title":"first","title":"last"}}', "fixture")

    def test_nested_parameter_constraints_are_enforced(self):
        schema = {"type": "object", "properties": {
            "journal_keys": {"type": "array", "items": {"type": "string", "enum": ["valid"]}},
            "max_pages_per_journal": {"type": "integer", "maximum": 100}}, "additionalProperties": False}
        with self.assertRaisesRegex(ProtocolError, r"journal_keys\[0\]"):
            validate_parameters(schema, {"journal_keys": ["bogus"]})
        with self.assertRaisesRegex(ProtocolError, "greater than the maximum"):
            validate_parameters(schema, {"max_pages_per_journal": 101})

    def test_array_output_items_are_validated(self):
        from dataclasses import replace
        from crawler_platform.protocol import FieldSpec
        manifest = load_manifest(ROOT / "crawler_packages" / "reference" / "baidu_baike")
        manifest = replace(manifest, fields=manifest.fields + (
            FieldSpec("authors", "array", False, schema={"type": "array", "items": {"type": "string"}}),))
        sample = json.loads((ROOT / "crawler_packages" / "reference" / "baidu_baike" / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        sample["authors"] = [123]
        with self.assertRaisesRegex(ProtocolError, r"authors\[0\]"):
            validate_item(manifest, sample)


if __name__ == "__main__":
    unittest.main()
