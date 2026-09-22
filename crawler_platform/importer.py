from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from crawler_platform.config import Settings
from crawler_platform.protocol import (
    load_manifest, package_digest, schema_digest, validate_runtime, validate_upgrade,
)
from crawler_platform.storage import PlatformStore


class PackageImporter:
    def __init__(self, settings: Settings, store: PlatformStore):
        self.settings = settings
        self.store = store

    def install(self, source_dir: Path) -> dict:
        source_dir = source_dir.resolve()
        manifest = load_manifest(source_dir)
        validate_runtime(manifest)
        try:
            existing = self.store.package(manifest.package_key)
        except KeyError:
            existing = None
        if existing and existing.get("active_artifact_path"):
            validate_upgrade(load_manifest(Path(existing["active_artifact_path"])), manifest)
        artifact_digest = package_digest(source_dir)
        schema_hash = schema_digest(manifest)
        artifact_dir = (
            self.settings.packages_dir / manifest.package_key
            / manifest.package_version / artifact_digest
        )
        row = self.store.register_installing(
            manifest, artifact_digest, schema_hash, artifact_dir,
        )
        if row.get("idempotent"):
            return {"package_key": manifest.package_key, "status": "ready", "idempotent": True}
        try:
            if not artifact_dir.exists():
                artifact_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_dir, artifact_dir)
            installed_manifest = load_manifest(artifact_dir)
            self._prepare_environment(installed_manifest, artifact_dir)
            self.store.create_or_upgrade_package_table(row["table_name"], installed_manifest)
            self.store.activate_package(
                row["id"], installed_manifest, artifact_digest, schema_hash, artifact_dir,
            )
            return {
                "id": row["id"], "package_key": manifest.package_key,
                "version": manifest.package_version, "table_name": row["table_name"],
                "status": "ready", "idempotent": False,
            }
        except Exception as exc:
            self.store.fail_install(manifest.package_key, f"{type(exc).__name__}: {exc}")
            raise

    def _prepare_environment(self, manifest, artifact_dir: Path) -> None:
        environment = self.settings.environments_dir / manifest.package_key / manifest.package_version
        python = self.environment_python(environment)
        if not python.exists():
            environment.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [sys.executable, "-m", "venv", str(environment)],
                check=True, timeout=120,
            )
        dependencies = artifact_dir / manifest.dependencies
        if dependencies.stat().st_size:
            subprocess.run(
                [str(python), "-m", "pip", "install", "--requirement", str(dependencies)],
                check=True, timeout=300,
            )

    @staticmethod
    def environment_python(environment: Path) -> Path:
        if sys.platform == "win32":
            return environment / "Scripts" / "python.exe"
        return environment / "bin" / "python"
