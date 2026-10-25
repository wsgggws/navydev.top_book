"""Browser-only guards and response hardening."""

from __future__ import annotations

from fastapi.testclient import TestClient


def secured_client(settings, engine):
    from lector.web import create_app

    secured = settings.__class__(**{**settings.__dict__, "token": "secret"})
    app = create_app(secured)
    app.state.ctx.engine = engine
    app.state.ctx.audio.engine = engine
    return TestClient(app)


def test_obvious_cli_user_agents_cannot_open_the_web_app(settings, engine):
    client = secured_client(settings, engine)

    blocked = client.get("/", headers={"user-agent": "curl/8.10.1"})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "BROWSER_ONLY"

    allowed = client.get("/", headers={"user-agent": "Mozilla/5.0"})
    assert allowed.status_code == 200
    assert allowed.headers["x-frame-options"] == "SAMEORIGIN"
    assert "default-src 'self'" in allowed.headers["content-security-policy"]


def test_public_api_allows_browser_terminal_and_admin_cli(settings, engine):
    client = secured_client(settings, engine)

    assert client.get(
        "/api/v1/books", headers={"user-agent": "curl/8.10.1"}
    ).status_code == 403
    assert client.get(
        "/api/v1/books",
        headers={
            "user-agent": "python-httpx/1.0",
            "X-Lector-Client": "terminal",
        },
    ).status_code == 200
    assert client.get(
        "/api/v1/books",
        headers={
            "user-agent": "python-httpx/1.0",
            "Authorization": "Bearer secret",
        },
    ).status_code == 200
    assert client.get(
        "/api/v1/health", headers={"user-agent": "curl/8.10.1"}
    ).status_code == 200


def test_public_host_without_a_token_allows_reads_but_disables_admin(
    settings, engine, epub2_bytes: bytes
):
    from lector.web import create_app

    public = settings.__class__(**{**settings.__dict__, "token": "", "host": "0.0.0.0"})
    app = create_app(public)
    app.state.ctx.engine = engine
    app.state.ctx.audio.engine = engine
    client = TestClient(app)
    domain_headers = {"Host": "navydev.top", "User-Agent": "Mozilla/5.0"}

    assert client.get("/", headers=domain_headers).status_code == 200
    assert client.get("/api/v1/books", headers=domain_headers).status_code == 200
    assert client.get(
        "/api/v1/books",
        headers={"Host": "navydev.top", "User-Agent": "curl/8.10.1"},
    ).status_code == 403
    assert client.get(
        "/api/v1/books",
        headers={
            "Host": "navydev.top",
            "User-Agent": "python-httpx/1.0",
            "X-Lector-Client": "terminal",
        },
    ).status_code == 200

    upload = client.post(
        "/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
        headers={
            "Host": "navydev.top",
            "Origin": "http://navydev.top",
            "User-Agent": "Mozilla/5.0",
        },
    )
    assert upload.status_code == 403
    assert upload.json()["error"]["code"] == "ADMIN_DISABLED"


def test_writes_require_same_origin_or_a_valid_token(
    settings, engine, epub2_bytes: bytes
):
    client = secured_client(settings, engine)
    upload = client.post(
        "/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
        headers={
            "Authorization": "Bearer secret",
            "User-Agent": "python-httpx/1.0",
        },
    )
    assert upload.status_code == 201
    book_id = upload.json()["book"]["book_id"]

    no_source = client.post(f"/api/v1/books/{book_id}/open")
    assert no_source.status_code == 403
    assert no_source.json()["error"]["code"] == "SAME_ORIGIN_REQUIRED"

    cross_site = client.post(
        f"/api/v1/books/{book_id}/open",
        headers={
            "Origin": "https://evil.example",
            "Sec-Fetch-Site": "cross-site",
        },
    )
    assert cross_site.status_code == 403

    same_origin = client.post(
        f"/api/v1/books/{book_id}/open",
        headers={
            "Origin": "http://testserver",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert same_origin.status_code == 200
    assert same_origin.json()["open_count"] == 1

    token_api = client.post(
        f"/api/v1/books/{book_id}/open",
        headers={"Authorization": "Bearer secret"},
    )
    assert token_api.status_code == 200
    assert token_api.json()["open_count"] == 2
