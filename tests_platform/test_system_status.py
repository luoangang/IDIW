import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, Mock

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.process_lock import ProcessLock
from crawler_platform.storage import PlatformStore


def test_system_status_distinguishes_api_from_stopped_workers():
    with tempfile.TemporaryDirectory() as directory:
        settings = replace(SETTINGS, runtime_dir=Path(directory), token="")
        store = Mock()
        store.operational_status.return_value = {"queued": 3, "running": 0, "overdue_monitors": 2, "recent_issues": []}
        with ProcessLock(settings.runtime_dir / "locks" / "serve.lock"):
            payload = create_app(settings, store).test_client().get("/api/v1/system/status").get_json()
        states = {row["role"]: row["state"] for row in payload["processes"]}
        assert states == {"serve": "running", "scheduler": "stopped", "worker-default": "stopped"}
        assert payload["collection"]["queued"] == 3
        assert payload["database"]["state"] == "ready"


def test_status_auth_and_database_failure_are_safe():
    settings = replace(SETTINGS, token="test-secret")
    store = Mock()
    store.operational_status.side_effect = RuntimeError("private-password")
    client = create_app(settings, store).test_client()
    assert client.get("/api/v1/system/status").status_code == 401
    response = client.get("/api/v1/system/status", headers={"Authorization": "Bearer test-secret"})
    assert response.status_code == 200
    assert response.get_json()["database"]["state"] == "unavailable"
    assert "private-password" not in response.get_data(as_text=True)


def test_status_queries_close_connection_and_return_counts():
    store = PlatformStore(SETTINGS)
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [[{"status": "queued", "total": 2}], [{"id": 7, "status": "failed"}]]
    cursor.fetchone.return_value = {"total": 4}
    store.connect = Mock(return_value=connection)
    result = store.operational_status()
    assert result == {"queued": 2, "running": 0, "overdue_monitors": 4, "recent_issues": [{"id": 7, "status": "failed"}]}
    connection.close.assert_called_once()
