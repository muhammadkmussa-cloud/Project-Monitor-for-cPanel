import pytest
import os
import httpx

# Run from host against exposed port, or from inside container against itself
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8080")
ADMIN_EMAIL = "admin@monitor.com"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def admin_token(base_url):
    """Get admin JWT token for testing."""
    resp = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    return data["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    """Authorization headers for admin requests."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def user_token(base_url, admin_headers):
    """Create a regular user and return their token."""
    # Create user
    resp = httpx.post(
        f"{base_url}/api/v1/users",
        headers=admin_headers,
        json={
            "client_id": "00000000-0000-0000-0000-000000000001",
            "email": "test_user@test.com",
            "name": "Test User",
            "password": "test-password-123",
            "role": "user",
        },
    )
    # Login as user
    resp = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": "test_user@test.com", "password": "test-password-123"},
    )
    if resp.status_code == 200:
        return resp.json()["token"]
    return None


@pytest.fixture(scope="session")
def user_headers(user_token):
    """Authorization headers for regular user requests."""
    if user_token:
        return {"Authorization": f"Bearer {user_token}"}
    return {}


@pytest.fixture(scope="session")
def default_client_id():
    return "00000000-0000-0000-0000-000000000001"


def pytest_collection_modifyitems(items):
    if not os.environ.get("TEST_BASE_URL"):
        for item in items:
            if item.path.name in {"test_api.py", "test_auth.py"}:
                item.add_marker(pytest.mark.skip(reason="Live integration tests require explicit TEST_BASE_URL and TEST_ADMIN_PASSWORD"))
