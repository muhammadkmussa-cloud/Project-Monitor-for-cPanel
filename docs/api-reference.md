# API access

Local base URL: `http://localhost:8080/api/v1`. The dashboard proxies the same API through port 3005.

Log in with `POST /auth/login` and a JSON body containing `email` and `password`. Send the returned token as `Authorization: Bearer <token>`. `GET /auth/me` validates the current account. Do not put passwords in URLs.

Platform administration and mutations require an active admin/owner. Tenant accounts can read their own projects, incidents, and analytics. API keys use `X-API-Key` and must be active, unexpired, and have appropriate resource scopes. New keys default to read scopes.

Common routes:

| Route | Purpose |
|---|---|
| `GET /projects`, `GET /projects/{id}` | Projects visible to this account |
| `POST /projects`, `PUT /projects/{id}` | Create/update project configuration |
| `GET /incidents`, `GET /incidents/{id}` | Incidents visible to this account |
| `GET /analytics/dashboard` | Current stored dashboard metrics |
| `GET /analytics/health-trends/{id}` | Daily recorded project health |
| `GET /settings`, `PUT /settings/{key}` | Platform preferences; update body is `{"value": ...}` |
| `POST /trigger-scan` | Queue a manual monitoring cycle (202) |
| `POST /monitoring/run` | Run scheduled checks for due projects |

Approving an incident records permission; it does not itself execute a fix. Execution requires its exact reviewed proposal, valid approval, and stored project connection. A proposal can be claimed only once. The scheduler never approves or executes remediation.

See the request models in `monitoring-agent/app/api/schemas.py` and handlers in `monitoring-agent/app/api/routes.py` for complete field contracts. Interactive API documentation is protected by authentication.
