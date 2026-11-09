"""Collect a small live sample with every active plugin without inserting records."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.executor import PackageExecutor
from crawler_platform.importer import PackageImporter
from crawler_platform.protocol import load_manifest, validate_parameters
from crawler_platform.storage import PlatformStore


def main():
    failed = []
    for package in PlatformStore(SETTINGS).list_packages():
        details = PlatformStore(SETTINGS).package(package["package_key"])
        artifact = Path(details["active_artifact_path"])
        manifest = load_manifest(artifact)
        execution_id = str(uuid.uuid4())
        work = SETTINGS.runs_dir / ("environment-smoke-" + execution_id)
        output = work / "output"
        output.mkdir(parents=True)
        parameters = {}
        if manifest.package_key == "magetech_journals":
            parameters = {"journal_keys": ["data_analysis"], "max_pages_per_journal": 1,
                          "request_delay_ms": 0}
        if manifest.package_key == "books_to_scrape":
            parameters = {"max_pages": 1, "request_delay_ms": 0}
        request = {"protocol_version": "1.0", "execution_id": execution_id,
                   "package_key": manifest.package_key, "package_version": manifest.package_version,
                   "query": "Light" if manifest.package_key == "books_to_scrape" else "人工智能",
                   "aliases": [], "limit": 1,
                   "parameters": validate_parameters(manifest.parameters_schema, parameters),
                   "cursor": None, "cursor_version": 0,
                   "time_range": {"from": None, "to": None},
                   "deadline_at": (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()}
        request_path = work / "request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        python = PackageImporter.environment_python(
            SETTINGS.environments_dir / manifest.package_key / manifest.package_version)
        try:
            with (work / "process.log").open("w", encoding="utf-8") as log:
                process = subprocess.run([str(python), str(artifact / manifest.entrypoint),
                                          "--request", str(request_path), "--output", str(output)],
                                         cwd=artifact, env=PackageExecutor._child_environment(python, work),
                                         stdout=log, stderr=subprocess.STDOUT, timeout=180)
            result = PackageExecutor._read_result(output, request, process.returncode, manifest.incremental)
            valid, rejected = PackageExecutor._read_items(output, manifest, 1)
            assert result["item_count"] == len(valid) + len(rejected)
            assert result["status"] != "failed" and not rejected and valid
            print(manifest.package_key, result["status"], "valid", len(valid), "rejected", len(rejected), flush=True)
        except Exception as exc:
            failed.append(manifest.package_key)
            print(manifest.package_key, "FAILED", str(exc), "logs", str(work), flush=True)
    if failed:
        raise SystemExit("Smoke failures: " + ", ".join(failed))


if __name__ == "__main__":
    main()
