import httpx


class TestRBAC:
    """Tests for Role-Based Access Control."""

    def test_admin_can_delete_client(self, base_url, admin_headers, default_client_id):
        """Admin should be able to delete clients."""
        # Create a client first to delete
        resp = httpx.post(
            f"{base_url}/api/v1/clients",
            headers=admin_headers,
            json={
                "client_name": "Delete Me",
                "email": "delete@test.com",
                "company": "Test",
            },
        )
        if resp.status_code == 201:
            client_id = resp.json()["client_id"]
            resp = httpx.delete(
                f"{base_url}/api/v1/clients/{client_id}",
                headers=admin_headers,
            )
            assert resp.status_code == 200

    def test_non_admin_cannot_delete_client(self, base_url, user_headers, default_client_id):
        """Regular user should NOT be able to delete clients."""
        resp = httpx.delete(
            f"{base_url}/api/v1/clients/{default_client_id}",
            headers=user_headers,
        )
        assert resp.status_code == 403
        assert "Admin access required" in resp.json()["detail"]

    def test_admin_can_create_invoice(self, base_url, admin_headers, default_client_id):
        """Admin should be able to create invoices."""
        resp = httpx.post(
            f"{base_url}/api/v1/billing/invoices",
            headers=admin_headers,
            params={
                "client_id": default_client_id,
                "plan": "starter",
                "billing_cycle": "monthly",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["plan"] == "starter"
        assert data["status"] == "pending"

    def test_non_admin_cannot_create_invoice(self, base_url, user_headers, default_client_id):
        """Regular user should NOT be able to create invoices."""
        resp = httpx.post(
            f"{base_url}/api/v1/billing/invoices",
            headers=user_headers,
            params={
                "client_id": default_client_id,
                "plan": "starter",
            },
        )
        assert resp.status_code == 403

    def test_admin_can_trigger_scan(self, base_url, admin_headers):
        """Admin should be able to trigger scans."""
        resp = httpx.post(
            f"{base_url}/api/v1/trigger-scan",
            headers=admin_headers,
        )
        assert resp.status_code in (200, 202)

    def test_non_admin_cannot_trigger_scan(self, base_url, user_headers):
        """Regular user should NOT be able to trigger scans."""
        resp = httpx.post(
            f"{base_url}/api/v1/trigger-scan",
            headers=user_headers,
        )
        assert resp.status_code == 403

    def test_non_admin_can_read_projects(self, base_url, user_headers):
        """Regular user should be able to read projects."""
        resp = httpx.get(
            f"{base_url}/api/v1/projects",
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_non_admin_can_read_billing_plans(self, base_url, user_headers):
        """Regular user should be able to read billing plans."""
        resp = httpx.get(
            f"{base_url}/api/v1/billing/plans",
            headers=user_headers,
        )
        assert resp.status_code == 200
        plans = resp.json()
        assert len(plans) == 3

    def test_non_admin_can_read_analytics(self, base_url, user_headers):
        """Regular user should be able to read analytics."""
        resp = httpx.get(
            f"{base_url}/api/v1/analytics/dashboard",
            headers=user_headers,
        )
        assert resp.status_code == 200

    def _create_project(self, base_url, headers):
        resp = httpx.post(
            f"{base_url}/api/v1/projects",
            headers=headers,
            json={
                "client_id": "00000000-0000-0000-0000-000000000001",
                "project_name": "RBAC Test Project",
                "domain": "test.example",
                "server_host": "test.example",
                "application_type": "php",
            },
        )
        assert resp.status_code == 201
        return resp.json()["project_id"]

    def test_admin_can_create_credential(self, base_url, admin_headers):
        """Admin should be able to store SSH credentials for a project."""
        pid = self._create_project(base_url, admin_headers)
        try:
            resp = httpx.post(
                f"{base_url}/api/v1/projects/{pid}/credentials",
                headers=admin_headers,
                json={
                    "name": "test-ssh",
                    "credential_type": "ssh",
                    "host": "test.example",
                    "port": 22,
                    "username": "user",
                    "password": "secret",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["host"] == "test.example"
            assert "password" not in data or data.get("password") is None
            # listing shows non-secret details of the stored credential
            listing = httpx.get(
                f"{base_url}/api/v1/projects/{pid}/credentials",
                headers=admin_headers,
            )
            assert listing.status_code == 200
            listed = [c for c in listing.json() if c["name"] == "test-ssh"]
            assert listed
            assert listed[0]["host"] == "test.example"
            assert listed[0]["username"] == "user"
            assert listed[0]["has_password"] is True
        finally:
            httpx.delete(f"{base_url}/api/v1/projects/{pid}", headers=admin_headers)

    def test_admin_can_delete_project(self, base_url, admin_headers):
        """Admin should be able to delete a project."""
        pid = self._create_project(base_url, admin_headers)
        resp = httpx.delete(
            f"{base_url}/api/v1/projects/{pid}",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    def test_non_admin_cannot_delete_project(self, base_url, user_headers, admin_headers):
        """Regular user should NOT be able to delete a project."""
        pid = self._create_project(base_url, admin_headers)
        resp = httpx.delete(
            f"{base_url}/api/v1/projects/{pid}",
            headers=user_headers,
        )
        assert resp.status_code == 403
        httpx.delete(f"{base_url}/api/v1/projects/{pid}", headers=admin_headers)

    def test_non_admin_cannot_create_credential(self, base_url, user_headers):
        """Regular user should NOT be able to store credentials (admin-only)."""
        resp = httpx.post(
            f"{base_url}/api/v1/projects/00000000-0000-0000-0000-000000000001/credentials",
            headers=user_headers,
            json={"credential_type": "ssh", "host": "x.example", "username": "u"},
        )
        assert resp.status_code == 403

    def test_settings_roundtrip(self, base_url, admin_headers):
        """Settings can be read and updated by admin."""
        resp = httpx.put(
            f"{base_url}/api/v1/settings/profile.name",
            headers=admin_headers,
            json={"value": "RBAC Test User"},
        )
        assert resp.status_code == 200
        listing = httpx.get(f"{base_url}/api/v1/settings", headers=admin_headers)
        assert listing.status_code == 200
        assert listing.json().get("profile.name") == "RBAC Test User"

    def test_incident_resolve_endpoint(self, base_url, admin_headers, default_client_id):
        """Resolving a non-existent incident returns 404."""
        resp = httpx.post(
            f"{base_url}/api/v1/incidents/00000000-0000-0000-0000-00000000dead/resolve",
            headers=admin_headers,
        )
        assert resp.status_code == 404
