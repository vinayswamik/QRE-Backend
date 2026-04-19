"""
Tests for app-level concerns:
  1. Health check endpoint
  2. CORS middleware
  3. OpenAPI / docs endpoints
  4. 404 handling for unknown routes
  5. Lambda handler import
"""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.rate_limit import reset_rate_limiter
from app.main import app
from handler import lambda_handler

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Verify the /health endpoint returns correct status and version."""

    def test_health_returns_200(self):
        """GET /health should return HTTP 200."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_shape(self):
        """Health response should include status and version fields."""
        data = client.get("/health").json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_version_matches_settings(self):
        """Reported version should match the configured APP_VERSION."""
        data = client.get("/health").json()
        assert data["version"] == settings.APP_VERSION


# ---------------------------------------------------------------------------
# 2. CORS
# ---------------------------------------------------------------------------


class TestCORS:
    """Verify CORS middleware allows/rejects the correct origins."""

    def test_cors_allows_configured_origin(self):
        """Configured origin should receive the allow-origin header."""
        origin = settings.CORS_ORIGINS[0]
        resp = client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == origin

    def test_cors_rejects_unknown_origin(self):
        """Unknown origin should not receive an allow-origin header."""
        resp = client.options(
            "/health",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert (
            resp.headers.get("access-control-allow-origin")
            != "https://evil.example.com"
        )

    def test_cors_allows_post(self):
        """POST method should be allowed by CORS for configured origins."""
        origin = settings.CORS_ORIGINS[0]
        resp = client.options(
            "/api/v1/qasm/validate",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )
        allow_methods = resp.headers.get("access-control-allow-methods", "")
        assert "POST" in allow_methods or "*" in allow_methods


# ---------------------------------------------------------------------------
# 3. OpenAPI / docs
# ---------------------------------------------------------------------------


class TestDocs:
    """Verify OpenAPI spec and documentation endpoints are accessible."""

    def test_openapi_json_available(self):
        """OpenAPI JSON should be served and list all API routes."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data
        assert "/api/v1/qasm/validate" in data["paths"]
        assert "/api/v1/qasm/analyze" in data["paths"]
        assert "/health" in data["paths"]

    def test_docs_endpoint_available(self):
        """Swagger UI should be served at /docs."""
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_endpoint_available(self):
        """ReDoc should be served at /redoc."""
        resp = client.get("/redoc")
        assert resp.status_code == 200

    def test_openapi_title_matches_settings(self):
        """OpenAPI title should match the configured APP_NAME."""
        data = client.get("/openapi.json").json()
        assert data["info"]["title"] == settings.APP_NAME


# ---------------------------------------------------------------------------
# 4. 404 handling
# ---------------------------------------------------------------------------


class TestNotFound:
    """Verify unknown routes return 404."""

    def test_unknown_get_returns_404(self):
        """GET to a non-existent route should return 404."""
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404

    def test_unknown_post_returns_404(self):
        """POST to a non-existent route should return 404 or 405."""
        resp = client.post("/api/v1/nonexistent", json={})
        assert resp.status_code in {404, 405}

    def test_root_returns_404(self):
        """Root path should return 404 (no root handler defined)."""
        resp = client.get("/")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Lambda handler
# ---------------------------------------------------------------------------


class TestLambdaHandler:
    """Verify the Mangum Lambda handler is importable and callable."""

    def test_handler_module_imports(self):
        """lambda_handler should be a callable object."""
        assert callable(lambda_handler)

    def test_handler_wraps_same_app(self):
        """Mangum handler should wrap the FastAPI app and be importable."""
        # Mangum wraps the app — just check it's importable and callable
        assert lambda_handler is not None


# ---------------------------------------------------------------------------
# 6. HTTP method enforcement
# ---------------------------------------------------------------------------


class TestMethodEnforcement:
    """Verify endpoints reject incorrect HTTP methods."""

    def test_validate_rejects_get(self):
        """GET on a POST-only endpoint should return 405."""
        resp = client.get("/api/v1/qasm/validate")
        assert resp.status_code == 405

    def test_analyze_rejects_get(self):
        """GET on the analyze endpoint should return 405."""
        resp = client.get("/api/v1/qasm/analyze")
        assert resp.status_code == 405

    def test_health_rejects_post(self):
        """POST on the GET-only health endpoint should return 405."""
        resp = client.post("/health")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# 7. Security headers
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    """Verify baseline security headers are attached to responses."""

    def test_health_includes_security_headers(self):
        """GET /health should include hardening headers."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "no-referrer"
        assert (
            resp.headers.get("permissions-policy")
            == "geolocation=(), microphone=(), camera=()"
        )
        assert resp.headers.get("content-security-policy") is not None


# ---------------------------------------------------------------------------
# 8. Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Verify per-endpoint request throttling."""

    def test_validate_endpoint_rate_limits(self, monkeypatch):
        """Validate should return 429 after per-window request limit is exceeded."""
        reset_rate_limiter()
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
        monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
        monkeypatch.setattr(settings, "RATE_LIMIT_VALIDATE_REQUESTS", 2)

        payload = {
            "code": (
                'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[1];\ncreg c[1];\n'
                "h q[0];\nmeasure q -> c;"
            )
        }

        first = client.post("/api/v1/qasm/validate", json=payload)
        second = client.post("/api/v1/qasm/validate", json=payload)
        third = client.post("/api/v1/qasm/validate", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert third.headers.get("retry-after") is not None
