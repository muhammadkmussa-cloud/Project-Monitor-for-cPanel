import httpx


class TestHealthEndpoint:
    """Tests for the public /health endpoint."""

    def test_health_returns_200(self, base_url):
        resp = httpx.get(f"{base_url}/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self, base_url):
        resp = httpx.get(f"{base_url}/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "monitoring-agent"


class TestLoginEndpoint:
    """Tests for the /auth/login endpoint."""

    def test_login_with_valid_credentials(self, base_url):
        resp = httpx.post(
            f"{base_url}/api/v1/auth/login",
            params={"email": "admin@monitor.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "admin@monitor.com"
        assert data["user"]["role"] == "admin"

    def test_login_with_invalid_password(self, base_url):
        resp = httpx.post(
            f"{base_url}/api/v1/auth/login",
            params={"email": "admin@monitor.com", "password": "wrong"},
        )
        assert resp.status_code in (401, 422)

    def test_login_with_nonexistent_user(self, base_url):
        resp = httpx.post(
            f"{base_url}/api/v1/auth/login",
            params={"email": "nobody@test.com", "password": "test"},
        )
        assert resp.status_code in (401, 422)


class TestProtectedEndpoints:
    """Tests for authentication on protected endpoints."""

    def test_projects_requires_auth(self, base_url):
        resp = httpx.get(f"{base_url}/api/v1/projects")
        assert resp.status_code == 401

    def test_projects_with_valid_token(self, base_url, admin_headers):
        resp = httpx.get(f"{base_url}/api/v1/projects", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_projects_with_invalid_token(self, base_url):
        resp = httpx.get(
            f"{base_url}/api/v1/projects",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_clients_requires_auth(self, base_url):
        resp = httpx.get(f"{base_url}/api/v1/clients")
        assert resp.status_code == 401

    def test_clients_with_valid_token(self, base_url, admin_headers):
        resp = httpx.get(f"{base_url}/api/v1/clients", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_incidents_requires_auth(self, base_url):
        resp = httpx.get(f"{base_url}/api/v1/incidents")
        assert resp.status_code == 401

    def test_incidents_with_valid_token(self, base_url, admin_headers):
        resp = httpx.get(f"{base_url}/api/v1/incidents", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_settings_requires_auth(self, base_url):
        resp = httpx.get(f"{base_url}/api/v1/settings")
        assert resp.status_code == 401

    def test_settings_with_valid_token(self, base_url, admin_headers):
        resp = httpx.get(f"{base_url}/api/v1/settings", headers=admin_headers)
        assert resp.status_code == 200
