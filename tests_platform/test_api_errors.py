from unittest.mock import Mock

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS


def test_http_errors_keep_their_status_codes():
    client = create_app(SETTINGS, Mock()).test_client()
    assert client.get("/not-an-endpoint").status_code == 404
    assert client.post("/health/live").status_code == 405


def test_unexpected_errors_are_logged_but_not_disclosed():
    store = Mock()
    store.list_packages.side_effect = RuntimeError("mysql://private:password@host/database")
    app = create_app(SETTINGS, store)
    with app.test_client() as client:
        response = client.get("/health/ready")
    assert response.status_code == 500
    payload = response.get_json()
    assert len(payload["reference"]) == 12
    assert "password" not in response.get_data(as_text=True)
    assert payload["error"] == "internal_error"
