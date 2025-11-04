import pytest
import requests


BASE_URL = "http://127.0.0.1:5001"


def test_web_server_healthcheck():
    try:
        response = requests.get(f"{BASE_URL}/api/auth/current", timeout=3)
    except requests.ConnectionError as exc:
        pytest.fail(f"Web server is not running on {BASE_URL}: {exc}")

    assert response.status_code in {200, 401, 403}
