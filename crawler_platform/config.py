from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("PLATFORM_MYSQL_DATABASE", "crawler_platform")
    host: str = os.getenv("PLATFORM_HOST", "127.0.0.1")
    port: int = int(os.getenv("PLATFORM_PORT", "8090"))
    token: str = os.getenv("PLATFORM_TOKEN", "")
    worker_poll_seconds: float = float(os.getenv("PLATFORM_WORKER_POLL_SECONDS", "2"))
    scheduler_poll_seconds: float = float(os.getenv("PLATFORM_SCHEDULER_POLL_SECONDS", "30"))
    package_timeout_seconds: int = int(os.getenv("PLATFORM_PACKAGE_TIMEOUT_SECONDS", "300"))
    runtime_dir: Path = PROJECT_ROOT / os.getenv(
        "PLATFORM_RUNTIME_DIR", "crawler_platform_runtime"
    )

    @property
    def packages_dir(self) -> Path:
        return self.runtime_dir / "packages"

    @property
    def environments_dir(self) -> Path:
        return self.runtime_dir / "environments"

    @property
    def runs_dir(self) -> Path:
        return self.runtime_dir / "runs"


SETTINGS = Settings()
