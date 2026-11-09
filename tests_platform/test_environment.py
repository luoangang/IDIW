import subprocess
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from crawler_platform.config import SETTINGS
from crawler_platform.importer import PackageImporter
from crawler_platform.protocol import ProtocolError, load_manifest, package_digest, validate_runtime
from crawler_platform.categories import discover_packages

ROOT = Path(__file__).resolve().parents[1]


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.artifact = ROOT / "crawler_packages" / "reference" / "baidu_baike"
        self.manifest = load_manifest(self.artifact)
        self.store = Mock(unsafe=True)
        self.importer = PackageImporter(SETTINGS, self.store)

    def test_current_packages_declare_python314(self):
        for path in discover_packages(ROOT / "crawler_packages") + discover_packages(ROOT / "packages_ready_to_import"):
            self.assertEqual("3.14", load_manifest(path).python_version)

    def test_missing_interpreter_is_unhealthy(self):
        health = self.importer._check_environment(Path("missing-python.exe"), self.manifest, self.artifact)
        self.assertFalse(health["healthy"])

    def test_dependency_failure_is_unhealthy(self):
        with patch("crawler_platform.importer.subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 0, "3.14.7", ""),
            subprocess.CalledProcessError(1, [], stderr="missing dependency"),
        ]):
            health = self.importer._check_environment(Path("python.exe"), self.manifest, self.artifact)
        self.assertFalse(health["healthy"])
        self.assertIn("missing dependency", health["error"])

    def test_idempotent_import_checks_and_repairs_environment(self):
        self.store.register_installing.return_value = {"idempotent": True}
        self.store.package.side_effect = KeyError("new")
        with patch.object(self.importer, "_prepare_environment", return_value=True) as prepare:
            result = self.importer.install(self.artifact)
        self.assertTrue(result["environment_repaired"])
        prepare.assert_called_once()
        self.store.activate_package.assert_not_called()

    def test_failed_build_preserves_existing_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = replace(SETTINGS, runtime_dir=Path(temporary))
            importer = PackageImporter(settings, self.store)
            environment = settings.environments_dir / self.manifest.package_key / self.manifest.package_version
            environment.mkdir(parents=True)
            sentinel = environment / "preserved.txt"
            sentinel.write_text("old environment")
            with patch.object(importer, "environment_health", return_value={"healthy": False}), \
                 patch("crawler_platform.importer.subprocess.run", side_effect=RuntimeError("build failed")):
                with self.assertRaisesRegex(RuntimeError, "build failed"):
                    importer._prepare_environment(self.manifest, self.artifact)
            self.assertTrue(sentinel.exists())
            self.assertFalse(environment.with_name(environment.name + ".repair.lock").exists())

    def test_runtime_mismatch_is_not_silently_accepted(self):
        with self.assertRaises(ProtocolError):
            validate_runtime(replace(self.manifest, python_version="3.9"))

    def test_real_idempotent_import_repairs_missing_environment_and_reuses_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = replace(SETTINGS, runtime_dir=Path(temporary))
            importer = PackageImporter(settings, self.store)
            artifact = (settings.packages_dir / self.manifest.category / self.manifest.package_key
                        / self.manifest.package_version / package_digest(self.artifact))
            shutil.copytree(self.artifact, artifact)
            self.store.package.side_effect = KeyError("mock registration")
            self.store.register_installing.return_value = {"idempotent": True}
            self.assertTrue(importer.install(self.artifact)["environment_repaired"])
            self.assertTrue(importer.environment_health(self.manifest, artifact)["healthy"])
            self.assertFalse(importer.install(self.artifact)["environment_repaired"])
