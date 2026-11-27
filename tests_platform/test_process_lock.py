import os
import subprocess
import sys
import tempfile
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from crawler_platform.process_lock import AlreadyRunning, ProcessLock, inspect_process_lock
from crawler_platform.config import SETTINGS
import platform_main


def test_role_lock_excludes_duplicate_and_can_be_reacquired():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "nested" / "serve.lock"
        with ProcessLock(path):
            assert inspect_process_lock(path)["state"] == "running"
            with pytest.raises(AlreadyRunning):
                with ProcessLock(path):
                    pytest.fail("duplicate lock was admitted")
        assert path.exists()
        assert inspect_process_lock(path)["state"] == "stopped"
        with ProcessLock(path):
            pass


def test_crashed_process_releases_lock_without_deleting_file():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "worker.lock"
        code = ("import os,sys; from pathlib import Path; "
                "from crawler_platform.process_lock import ProcessLock; "
                "lock=ProcessLock(Path(sys.argv[1])); lock.__enter__(); os._exit(23)")
        result = subprocess.run([sys.executable, "-c", code, str(path)], timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        assert result.returncode == 23
        with ProcessLock(path):
            pass


def test_different_worker_instances_are_independent():
    with tempfile.TemporaryDirectory() as directory:
        with ProcessLock(Path(directory) / "worker-first.lock"):
            with ProcessLock(Path(directory) / "worker-second.lock"):
                pass


def test_inspecting_missing_lock_does_not_create_files():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "missing" / "serve.lock"
        assert inspect_process_lock(path) == {"state": "stopped"}
        assert not path.parent.exists()


def test_service_errors_are_logged_and_lock_is_released(monkeypatch, tmp_path):
    monkeypatch.setattr(platform_main, "SETTINGS", replace(SETTINGS, runtime_dir=tmp_path))
    original_level = logging.getLogger().level
    def fail():
        raise RuntimeError("fixture worker failure")
    with pytest.raises(RuntimeError, match="fixture worker failure"):
        platform_main.run_service("worker-fixture", fail)
    text = (tmp_path / "logs/worker-fixture.log").read_text(encoding="utf-8")
    assert "fixture worker failure" in text
    assert "+08:00" in text
    assert inspect_process_lock(tmp_path / "locks/worker-fixture.lock")["state"] == "stopped"
    assert logging.getLogger().level == original_level
