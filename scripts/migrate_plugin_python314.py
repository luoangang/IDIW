"""Publish the maintained Python 3.14 packages and check their active environments."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.importer import PackageImporter
from crawler_platform.protocol import load_manifest
from crawler_platform.storage import PlatformStore
from crawler_platform.categories import discover_packages


def main():
    importer = PackageImporter(SETTINGS, PlatformStore(SETTINGS))
    paths = discover_packages(ROOT / "crawler_packages")
    paths += discover_packages(ROOT / "packages_ready_to_import")
    for path in paths:
        print(importer.install(path), flush=True)
        package = importer.store.package(load_manifest(path).package_key)
        artifact = Path(package["active_artifact_path"])
        health = importer.environment_health(load_manifest(artifact), artifact)
        print(package["package_key"], health, flush=True)
        if not health["healthy"]:
            raise RuntimeError("environment migration failed")


if __name__ == "__main__":
    main()
