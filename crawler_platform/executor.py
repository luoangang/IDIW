from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from crawler_platform.config import Settings
from crawler_platform.importer import PackageImporter
from crawler_platform.protocol import ProtocolError, load_manifest, strict_json_loads, validate_item
from crawler_platform.storage import PlatformStore, json_dump


class PackageExecutor:
    def __init__(self, settings: Settings, store: PlatformStore):
        self.settings = settings
        self.store = store

    def execute(self, claimed: dict[str, Any]) -> dict[str, int] | None:
        artifact = Path(claimed["artifact_path"])
        manifest = load_manifest(artifact)
        work_dir = self.settings.runs_dir / claimed["execution_id"]
        output_dir = work_dir / "output"
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        request = dict(claimed["request"])
        request["deadline_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=self.settings.package_timeout_seconds)
        ).isoformat().replace("+00:00", "Z")
        request_path = work_dir / "request.json"
        request_path.write_text(json_dump(request), encoding="utf-8")
        log_path = work_dir / "process.log"
        environment = self.settings.environments_dir / manifest.package_key / manifest.package_version
        python = PackageImporter.environment_python(environment)
        command = [
            str(python), str(artifact / manifest.entrypoint),
            "--request", str(request_path), "--output", str(output_dir),
        ]
        child_env = self._child_environment(python, work_dir)
        for name in manifest.secret_names:
            env_name = f"CRAWLER_SECRET_{name}"
            if env_name in os.environ:
                child_env[env_name] = os.environ[env_name]
        started = time.monotonic()
        try:
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    command,
                    cwd=artifact,
                    env=child_env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=self.settings.package_timeout_seconds,
                    check=False,
                )
        except subprocess.TimeoutExpired:
            self.store.fail_package_run(
                claimed["id"], claimed["lease_token"], "timed_out", "TIMEOUT",
                f"package exceeded {self.settings.package_timeout_seconds} seconds",
                None, work_dir, log_path,
            )
            return None
        except Exception as exc:
            self.store.fail_package_run(
                claimed["id"], claimed["lease_token"], "failed", "PROCESS_ERROR",
                f"{type(exc).__name__}: {exc}", None, work_dir, log_path,
            )
            return None
        try:
            result = self._read_result(output_dir, request, completed.returncode, manifest.incremental)
            valid, rejected = self._read_items(output_dir, manifest, request["limit"])
            if result["item_count"] != len(valid) + len(rejected):
                raise ProtocolError("result.item_count does not match items.jsonl")
            if result["status"] == "failed":
                error = result.get("error") or {}
                self.store.fail_package_run(
                    claimed["id"], claimed["lease_token"], "failed",
                    str(error.get("code", "PACKAGE_FAILED")),
                    str(error.get("message", "package reported failure")),
                    completed.returncode, work_dir, log_path,
                )
                return None
            if completed.returncode != 0:
                raise ProtocolError("successful result requires exit code 0")
            rejected_path = output_dir / "rejected.jsonl"
            if rejected:
                rejected_path.write_text(
                    "".join(json_dump(row) + "\n" for row in rejected), encoding="utf-8"
                )
            result["duration_seconds"] = round(time.monotonic() - started, 6)
            return self.store.ingest(
                claimed, manifest, valid, len(rejected), result,
                completed.returncode, work_dir, log_path,
            )
        except Exception as exc:
            self.store.fail_package_run(
                claimed["id"], claimed["lease_token"], "failed", "PROTOCOL_ERROR",
                f"{type(exc).__name__}: {exc}", completed.returncode, work_dir, log_path,
            )
            return None

    @staticmethod
    def _child_environment(python: Path, work_dir: Path) -> dict[str, str]:
        path_parts = []
        if sys.platform == "win32":
            # Conda places OpenSSL's transitive DLLs outside the venv. Resolve
            # the base prefix from pyvenv.cfg so HTTPS works for background workers.
            config = python.parent.parent / "pyvenv.cfg"
            try:
                home_line = next(
                    line for line in config.read_text(encoding="utf-8").splitlines()
                    if line.lower().startswith("home =")
                )
                base_prefix = Path(home_line.split("=", 1)[1].strip())
            except (FileNotFoundError, StopIteration):
                base_prefix = Path(sys.base_prefix)
            for candidate in (base_prefix / "Library" / "bin", base_prefix / "DLLs"):
                if candidate.is_dir():
                    path_parts.append(str(candidate))
        inherited_path = os.environ.get("PATH", "")
        if inherited_path:
            path_parts.append(inherited_path)
        return {
            "PATH": os.pathsep.join(path_parts),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "TEMP": os.environ.get("TEMP", str(work_dir)),
            "TMP": os.environ.get("TMP", str(work_dir)),
            "PYTHONIOENCODING": "utf-8",
        }

    @staticmethod
    def _read_result(output_dir: Path, request: dict[str, Any], exit_code: int,
                     incremental: bool) -> dict[str, Any]:
        path = output_dir / "result.json"
        try:
            result = strict_json_loads(path.read_text(encoding="utf-8"), "result.json")
        except FileNotFoundError as exc:
            raise ProtocolError("result.json is missing") from exc
        required = {"protocol_version", "execution_id", "status", "item_count", "next_cursor", "has_more", "warnings", "error"}
        if not isinstance(result, dict) or set(result) != required:
            raise ProtocolError("result.json fields do not match protocol")
        if result["protocol_version"] != "1.0" or result["execution_id"] != request["execution_id"]:
            raise ProtocolError("result does not match request")
        if result["status"] not in {"completed", "partial", "failed"}:
            raise ProtocolError("invalid result status")
        if not isinstance(result["item_count"], int) or result["item_count"] < 0:
            raise ProtocolError("item_count must be non-negative")
        if not isinstance(result["has_more"], bool) or not isinstance(result["warnings"], list):
            raise ProtocolError("invalid result flags")
        if result["has_more"] and result["next_cursor"] is None:
            raise ProtocolError("has_more requires next_cursor")
        if not incremental and (result["next_cursor"] is not None or result["has_more"]):
            raise ProtocolError("non-incremental package returned cursor")
        if result["status"] in {"completed", "partial"} and exit_code != 0:
            raise ProtocolError("completed/partial result requires exit code 0")
        if result["status"] == "failed" and exit_code == 0:
            raise ProtocolError("failed result requires non-zero exit code")
        return result

    @staticmethod
    def _read_items(output_dir: Path, manifest, limit: int) -> tuple[list[dict], list[dict]]:
        path = output_dir / "items.jsonl"
        if not path.exists():
            raise ProtocolError("items.jsonl is missing")
        valid: list[dict] = []
        rejected: list[dict] = []
        record_count = 0
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                record_count += 1
                if record_count > limit:
                    raise ProtocolError("items exceed request.limit")
                try:
                    parsed = strict_json_loads(raw, f"items.jsonl line {line_number}")
                    valid.append(validate_item(manifest, parsed))
                except Exception as exc:
                    rejected.append({"line": line_number, "error": str(exc), "raw": raw[:1000]})
        return valid, rejected


class Worker:
    def __init__(self, settings: Settings, store: PlatformStore):
        self.settings = settings
        self.store = store
        self.executor = PackageExecutor(settings, store)
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}"

    def run_once(self) -> bool:
        claimed = self.store.claim_package_run(self.worker_id)
        if not claimed:
            return False
        self.executor.execute(claimed)
        return True

    def run_forever(self) -> None:
        while True:
            if not self.run_once():
                time.sleep(self.settings.worker_poll_seconds)


class Scheduler:
    def __init__(self, settings: Settings, store: PlatformStore):
        self.settings = settings
        self.store = store

    def run_forever(self) -> None:
        while True:
            self.store.enqueue_due_monitors()
            time.sleep(self.settings.scheduler_poll_seconds)
