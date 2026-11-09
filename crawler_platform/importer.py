from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from crawler_platform.config import Settings
from crawler_platform.categories import CATEGORIES
from crawler_platform.protocol import (
    ProtocolError, load_manifest, package_digest, schema_digest, validate_runtime, validate_upgrade,
)
from crawler_platform.storage import PlatformStore


class PackageImporter:
    def __init__(self, settings: Settings, store: PlatformStore):
        self.settings = settings
        self.store = store

    def install(self, source_dir: Path) -> dict:
        source_dir = source_dir.resolve()
        manifest = load_manifest(source_dir)
        if source_dir.parent.name in CATEGORIES and source_dir.parent.name != manifest.category:
            raise ProtocolError("package directory category does not match manifest.category")
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
            self.settings.packages_dir / manifest.category / manifest.package_key
            / manifest.package_version / artifact_digest
        )
        row = self.store.register_installing(
            manifest, artifact_digest, schema_hash, artifact_dir,
        )
        if row.get("idempotent"):
            artifact_dir = Path(row.get("active_artifact_path") or artifact_dir)
            repaired = self._prepare_environment(manifest, artifact_dir)
            return {"package_key": manifest.package_key, "version": manifest.package_version,
                    "status": "ready", "idempotent": True, "environment_repaired": repaired}
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

    def environment_health(self, manifest, artifact_dir: Path) -> dict:
        environment = self.settings.environments_dir / manifest.package_key / manifest.package_version
        python = self.environment_python(environment)
        return self._check_environment(python, manifest, artifact_dir)

    @staticmethod
    def _check_environment(python: Path, manifest, artifact_dir: Path) -> dict:
        probe = """import sys, ssl, importlib.metadata as metadata
from pathlib import Path
from pip._vendor.packaging.requirements import Requirement
assert '.'.join(map(str, sys.version_info[:2])) == sys.argv[1], 'Python version mismatch'
ssl.create_default_context()
for line in Path(sys.argv[2]).read_text(encoding='utf-8-sig').splitlines():
    line = line.strip()
    if not line or line.startswith('#'): continue
    requirement = Requirement(line)
    if requirement.marker and not requirement.marker.evaluate(): continue
    assert metadata.version(requirement.name) in requirement.specifier, 'Requirement mismatch: ' + line
print(sys.version.split()[0])
"""
        try:
            result = subprocess.run(
                [str(python), "-I", "-c", probe, manifest.python_version,
                 str(artifact_dir / manifest.dependencies)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, check=True,
            )
            subprocess.run([str(python), "-m", "pip", "check"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=30, check=True)
            if sys.platform == "win32":
                subprocess.run([str(python.parent / "pip.exe"), "--version"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=30, check=True)
            return {"healthy": True, "python_version": result.stdout.strip()}
        except (OSError, subprocess.SubprocessError) as exc:
            detail = getattr(exc, "stderr", None) or getattr(exc, "stdout", None) or str(exc)
            return {"healthy": False, "error": str(detail)[-2000:]}

    def rebuild_environment(self, package_key: str) -> dict:
        package = self.store.package(package_key)
        artifact = Path(package["active_artifact_path"])
        manifest = load_manifest(artifact)
        validate_runtime(manifest)
        self._prepare_environment(manifest, artifact, force=True)
        return {"package_key": package_key, "status": "ready", "environment_repaired": True}

    def _prepare_environment(self, manifest, artifact_dir: Path, force: bool = False) -> bool:
        validate_runtime(manifest)
        environment = self.settings.environments_dir / manifest.package_key / manifest.package_version
        if not force and self.environment_health(manifest, artifact_dir)["healthy"]:
            return False
        environment.parent.mkdir(parents=True, exist_ok=True)
        lock = environment.with_name(environment.name + ".repair.lock")
        try:
            lock_handle = lock.open("x")
        except FileExistsError as exc:
            raise ProtocolError("environment is already being rebuilt") from exc
        staging = environment.with_name(environment.name + ".building-" + uuid.uuid4().hex)
        backup = environment.with_name(environment.name + ".backup-" + uuid.uuid4().hex)
        try:
            self.store.assert_package_idle(manifest.package_key)
            if environment.exists():
                environment.rename(backup)
            try:
                # Build at the final path: Windows console launchers embed absolute paths.
                subprocess.run(
                    [sys.executable, "-m", "venv", str(environment)],
                    check=True, timeout=120,
                )
                dependencies = artifact_dir / manifest.dependencies
                python = self.environment_python(environment)
                if dependencies.read_text(encoding="utf-8-sig").strip():
                    subprocess.run(
                        [str(python), "-m", "pip", "install", "--requirement", str(dependencies)],
                        check=True, timeout=300,
                    )
                health = self.environment_health(manifest, artifact_dir)
                if not health["healthy"]:
                    raise ProtocolError(f"new environment failed health check: {health['error']}")
            except Exception:
                if environment.exists():
                    environment.rename(staging)
                if backup.exists():
                    backup.rename(environment)
                raise
            return True
        finally:
            lock_handle.close()
            lock.unlink()

    @staticmethod
    def environment_python(environment: Path) -> Path:
        if sys.platform == "win32":
            return environment / "Scripts" / "python.exe"
        return environment / "bin" / "python"
