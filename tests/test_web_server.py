import os

import pytest
import requests


BASE_URL = os.getenv("TEST_WEB_SERVER_BASE_URL", "http://127.0.0.1:5001")


def _request(method: str, path: str, **kwargs):
    try:
        return requests.request(method, f"{BASE_URL}{path}", timeout=3, **kwargs)
    except requests.ConnectionError as exc:
        pytest.fail(f"Web server is not running on {BASE_URL}: {exc}")


def test_web_server_healthcheck():
    response = _request("get", "/api/auth/current")
    assert response.status_code in {200, 401, 403}


def test_login_endpoint_handles_invalid_credentials():
    response = _request(
        "post",
        "/api/auth/login",
        json={"username": "__no_user__", "password": "wrong"}
    )

    assert response.status_code in {200, 401, 403}
    data = response.json()
    assert 'success' in data


def test_tags_endpoint_returns_json_payload():
    response = _request("get", "/api/tags")
    assert response.status_code == 200
    data = response.json()
    assert data['success'] in {True, False}
