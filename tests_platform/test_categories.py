import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from crawler_platform.api import create_app
from crawler_platform.categories import CATEGORIES, discover_packages, normalize_category
from crawler_platform.config import SETTINGS
from crawler_platform.importer import PackageImporter
from crawler_platform.package_layout import copy_categorized_artifact, migrate_package_layout
from crawler_platform.protocol import ProtocolError, load_manifest, package_digest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "crawler_packages" / "reference" / "baidu_baike"


class CategoryTests(unittest.TestCase):
    def test_six_categories_and_legacy_aliases(self):
        self.assertEqual(6, len(CATEGORIES))
        self.assertEqual("reference", normalize_category("encyclopedia"))
        self.assertEqual("reference", normalize_category("books"))
        self.assertEqual("academic", normalize_category("paper"))
        for value in ("../bad", "arbitrary", None, []):
            with self.assertRaises(ValueError):
                normalize_category(value)

    def test_discovery_and_declared_categories(self):
        paths = discover_packages(ROOT / "crawler_packages")
        self.assertGreaterEqual(len(paths), 4)
        for path in paths:
            self.assertEqual(path.parent.name, load_manifest(path).category)
        self.assertEqual([SAMPLE], discover_packages(SAMPLE))

    def test_mismatched_directory_rejected_before_database_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "news" / "baidu_baike"
            shutil.copytree(SAMPLE, source)
            store = Mock()
            with self.assertRaisesRegex(ProtocolError, "directory category"):
                PackageImporter(SETTINGS, store).install(source)
            store.package.assert_not_called()

    def test_new_import_uses_category_and_legacy_reimport_keeps_registered_path(self):
        store = Mock(unsafe=True)
        store.package.side_effect = KeyError("new")
        store.register_installing.return_value = {"idempotent": True, "active_artifact_path": str(SAMPLE)}
        importer = PackageImporter(SETTINGS, store)
        with patch.object(importer, "_prepare_environment", return_value=False) as prepare:
            importer.install(SAMPLE)
        registered_path = store.register_installing.call_args.args[3]
        self.assertEqual("reference", registered_path.relative_to(SETTINGS.packages_dir).parts[0])
        self.assertEqual(SAMPLE, prepare.call_args.args[1])

    def test_artifact_copy_preserves_digest_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "baidu_baike" / "1.0.2" / "digest"
            shutil.copytree(SAMPLE, source)
            digest = package_digest(source)
            target = copy_categorized_artifact(root, source)
            self.assertEqual(root / "reference" / "baidu_baike" / "1.0.2" / "digest", target)
            self.assertEqual(digest, package_digest(target))
            self.assertTrue(source.exists())
            self.assertEqual(target, copy_categorized_artifact(root, source))
            (target / "README.md").write_text("different")
            with self.assertRaisesRegex(ProtocolError, "different contents"):
                copy_categorized_artifact(root, source)

    def test_copy_rejects_outside_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ProtocolError, "outside"):
                copy_categorized_artifact(Path(temporary), SAMPLE)

    def test_category_endpoint(self):
        client = create_app(replace(SETTINGS, token=""), Mock()).test_client()
        response = client.get("/api/v1/categories")
        self.assertEqual(200, response.status_code)
        self.assertEqual(list(CATEGORIES), [row["key"] for row in response.get_json()])

    def test_migration_updates_paths_and_category_filters_in_one_transaction(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = replace(SETTINGS, runtime_dir=Path(temporary))
            source = settings.packages_dir / "baidu_baike" / "1.0.2" / "digest"
            shutil.copytree(SAMPLE, source)
            store = MagicMock()
            connection = store.connect.return_value
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.fetchall.side_effect = [
                [{"id": 1, "category": "encyclopedia", "active_artifact_path": str(source)}],
                [{"id": 3, "artifact_path": str(source)}],
                [{"id": 2, "selected_categories_json": '["encyclopedia","books","paper"]'}],
            ]
            result = migrate_package_layout(settings, store)
            self.assertEqual([1], result["updated_package_ids"])
            updates = [(call.args[0], call.args[1]) for call in cursor.execute.call_args_list if len(call.args) > 1]
            self.assertEqual(3, len(updates))
            self.assertEqual('[' + '"reference","academic"' + ']', updates[-1][1][0])
            connection.commit.assert_called_once()
            connection.rollback.assert_not_called()
            self.assertTrue(source.exists())

    def test_migration_failure_rolls_back_metadata_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = replace(SETTINGS, runtime_dir=Path(temporary))
            store = MagicMock()
            connection = store.connect.return_value
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.fetchall.side_effect = [
                [{"id": 1, "category": "news", "active_artifact_path": str(settings.packages_dir / "missing")}], [], []]
            with self.assertRaises(ProtocolError):
                migrate_package_layout(settings, store)
            connection.rollback.assert_called_once()
            connection.commit.assert_not_called()
