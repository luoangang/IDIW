"""OS-owned local role locks; a crashed process cannot leave a stale held lock."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class AlreadyRunning(RuntimeError):
    pass


class ProcessLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            if self.path.stat().st_size == 0:
                handle.write(b"\n")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise AlreadyRunning(f"服务已经运行，不重复启动。进程锁：{self.path}") from exc
            self.handle = handle
            # The first byte remains locked; metadata is diagnostic, never used to decide liveness.
            handle.seek(1)
            handle.truncate(1)
            handle.write(json.dumps({"pid": os.getpid(), "host": socket.gethostname(),
                                     "started_at": datetime.now(timezone.utc).isoformat()}).encode("utf-8"))
            handle.flush()
            return self
        except BaseException:
            self.handle = None
            handle.close()
            raise

    def __exit__(self, *exc_info):
        if self.handle is not None:
            try:
                self.handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None


def inspect_process_lock(path: Path):
    """Probe the OS lock, not a stale PID file. This is local CLI process status only."""
    try:
        handle = Path(path).open("r+b")
    except FileNotFoundError:
        return {"state": "stopped"}
    except OSError:
        return {"state": "unknown"}
    with handle:
        try:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return {"state": "stopped"}
        except OSError:
            # A held lock proves only process presence, not successful collection or a healthy loop.
            try:
                handle.seek(1)
                metadata = json.loads(handle.read(4096))
                return {"state": "running", "pid": metadata.get("pid"), "started_at": metadata.get("started_at")}
            except (OSError, ValueError, AttributeError):
                return {"state": "running"}
