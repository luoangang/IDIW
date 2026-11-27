from dataclasses import replace
from unittest.mock import Mock

import pytest

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS


@pytest.mark.parametrize("origin", ["https://attacker.example", "null", "http://localhost:9000", "http://user@localhost", "garbage"])
def test_foreign_websites_cannot_write_to_local_management(origin):
    store = Mock()
    client = create_app(replace(SETTINGS, token=""), store).test_client()
    response = client.post("/api/v1/packages/import", json={"path": "arbitrary"}, headers={"Origin": origin})
    assert response.status_code == 403
    assert response.get_json()["error"] == "cross_origin_request"
    store.register_installing.assert_not_called()


def test_cross_site_browser_metadata_blocks_opaque_post():
    client = create_app(replace(SETTINGS, token=""), Mock()).test_client()
    response = client.post("/api/v1/assistant/preview", json={}, headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


def test_same_origin_and_non_browser_requests_keep_existing_api_behavior():
    client = create_app(replace(SETTINGS, token=""), Mock()).test_client()
    for headers in ({}, {"Origin": "http://localhost"}, {"Origin": "http://localhost:80", "Sec-Fetch-Site": "same-origin"}):
        # Body validation, not the origin guard, rejects this intentionally incomplete draft request.
        assert client.post("/api/v1/assistant/preview", json={}, headers=headers).status_code == 422


def test_untrusted_host_is_rejected_even_for_read_requests():
    client = create_app(replace(SETTINGS, token=""), Mock()).test_client()
    assert client.get("/health/live", base_url="http://rebind.attacker.example").status_code == 400
    assert client.get("/health/live", base_url="http://127.0.0.1:8090").status_code == 200


def test_reverse_proxy_public_origin_must_be_explicitly_configured():
    settings = replace(SETTINGS, token="", trusted_hosts=("platform.example",), public_origin="https://platform.example")
    client = create_app(settings, Mock()).test_client()
    response = client.post("/api/v1/assistant/preview", base_url="http://platform.example", json={},
                           headers={"Origin": "https://platform.example"})
    assert response.status_code == 422
    assert client.post("/api/v1/assistant/preview", base_url="http://platform.example", json={},
                       headers={"Origin": "https://attacker.example"}).status_code == 403


def test_forwarded_headers_do_not_bypass_host_or_origin_validation():
    client = create_app(replace(SETTINGS, token=""), Mock()).test_client()
    response = client.post("/api/v1/assistant/preview", json={}, headers={
        "Origin": "https://attacker.example", "X-Forwarded-Host": "attacker.example", "X-Forwarded-Proto": "https",
    })
    assert response.status_code == 403


def test_invalid_security_configuration_fails_at_startup():
    with pytest.raises(ValueError, match="TRUSTED_HOSTS"):
        create_app(replace(SETTINGS, trusted_hosts=()), Mock())
    with pytest.raises(ValueError, match="PUBLIC_ORIGIN"):
        create_app(replace(SETTINGS, public_origin="https://platform.example/path"), Mock())
