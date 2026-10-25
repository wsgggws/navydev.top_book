"""Exercise the Compose trust configuration through Uvicorn's actual stack."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
import uvicorn
from fastapi import Request
from fastapi.testclient import TestClient

from lector.api import deps
from lector.web import create_app

COMPOSE = Path(__file__).resolve().parent.parent / 'docker-compose.yml'
GATEWAY = '172.30.81.1'


def compose_default_trust(gateway: str | None = None) -> str | None:
    # Read the actual deployment default rather than duplicating it in fixtures.
    compose = re.sub(
        r'\$\{LECTOR_PROXY_GATEWAY:-([^}]+)\}',
        lambda match: gateway if gateway is not None else match.group(1),
        COMPOSE.read_text(),
    )
    match = re.search(r'FORWARDED_ALLOW_IPS:\s*\$\{FORWARDED_ALLOW_IPS:-([^}]+)\}', compose)
    return match.group(1) if match else None


@pytest.fixture
def proxy_stack(settings, engine, epub2_bytes, monkeypatch):
    app = create_app(replace(settings, host='0.0.0.0', base_path='/ebook', token=''))
    app.state.ctx.engine = engine
    app.state.ctx.audio.engine = engine
    book_id = app.state.ctx.store.ingest(epub2_bytes).book.book_id

    @app.get('/ebook/proxy-probe', include_in_schema=False)
    async def probe(request: Request) -> dict[str, str]:
        return {'scheme': request.url.scheme, 'client': deps.client_address(request)}

    app.router.routes.insert(0, app.router.routes.pop())

    def make(peer: str, override: str | None = None, gateway: str | None = None) -> TestClient:
        trusted = override if override is not None else compose_default_trust(gateway)
        if trusted is None:
            monkeypatch.delenv('FORWARDED_ALLOW_IPS', raising=False)
        else:
            monkeypatch.setenv('FORWARDED_ALLOW_IPS', trusted)
        # This follows lector-server: Config reads FORWARDED_ALLOW_IPS from env,
        # then load() installs the real ProxyHeadersMiddleware outside FastAPI.
        config = uvicorn.Config(app, lifespan='off', log_config=None)
        config.load()
        return TestClient(config.loaded_app, base_url='http://navydev.top', client=(peer, 50000),
                          headers={'User-Agent': 'Mozilla/5.0'})

    return app, book_id, make


@pytest.mark.parametrize('peer', [GATEWAY, '127.0.0.1', '::1'])
def test_trusted_proxy_restores_https_and_open_works(proxy_stack, peer):
    app, book_id, make = proxy_stack
    client = make(peer)
    headers = {'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '203.0.113.9',
               'Origin': 'https://navydev.top', 'Sec-Fetch-Site': 'same-origin'}
    probe = client.get('/ebook/proxy-probe', headers=headers).json()
    opened = client.post(f'/ebook/api/v1/books/{book_id}/open', headers=headers)
    assert opened.status_code == 200
    assert probe == {'scheme': 'https', 'client': '203.0.113.9'}
    assert opened.json()['open_count'] == 1
    # Proxy trust provides request metadata, never a local admin exemption.
    denied = client.delete(f'/ebook/api/v1/books/{book_id}', headers=headers)
    assert denied.status_code == 403
    assert denied.json()['error']['code'] == 'ADMIN_DISABLED'


@pytest.mark.parametrize('peer', ['203.0.113.10', '172.19.0.1', '172.30.81.2'])
def test_untrusted_peer_cannot_forge_https_or_client_ip(proxy_stack, peer):
    app, book_id, make = proxy_stack
    client = make(peer)
    headers = {'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '198.51.100.8',
               'Origin': 'https://navydev.top'}
    assert client.get('/ebook/proxy-probe', headers=headers).json() == {'scheme': 'http', 'client': peer}
    response = client.post(f'/ebook/api/v1/books/{book_id}/open', headers=headers)
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'SAME_ORIGIN_REQUIRED'
    assert app.state.ctx.store.get_book(book_id).open_count == 0


@pytest.mark.parametrize('xff', [
    '198.51.100.8, 203.0.113.9',
    '127.0.0.1, 203.0.113.9',
    '172.30.81.1, 198.51.100.8, 203.0.113.9, 172.30.81.1',
])
def test_spoofed_xff_prefix_cannot_change_rate_limit_identity(proxy_stack, monkeypatch, xff):
    app, _, make = proxy_stack
    client = make(GATEWAY)
    headers = {'X-Forwarded-Proto': 'https', 'X-Forwarded-For': xff}
    assert client.get('/ebook/proxy-probe', headers=headers).json() == {'scheme': 'https', 'client': '203.0.113.9'}
    monkeypatch.setattr(deps, 'READ_LIMIT', 1)
    app.state.ctx.limiter.check('read', '203.0.113.9', 1)
    denied = client.get('/ebook/api/v1/books', headers=headers)
    assert denied.status_code == 429
    assert int(denied.headers['retry-after']) > 0
    # Another real client behind the same gateway has its own budget.
    assert client.get('/ebook/api/v1/books', headers={**headers, 'X-Forwarded-For': '203.0.113.11'}).status_code == 200


def test_private_client_in_bridge_subnet_is_not_treated_as_a_proxy(proxy_stack):
    _, _, make = proxy_stack
    response = make(GATEWAY).get('/ebook/proxy-probe', headers={
        'X-Forwarded-For': '198.51.100.8, 172.30.81.44', 'X-Forwarded-Proto': 'https',
    })
    assert response.json() == {'scheme': 'https', 'client': '172.30.81.44'}


def test_untrusted_peer_cannot_reset_budget_with_xff(proxy_stack, monkeypatch):
    app, _, make = proxy_stack
    peer = '203.0.113.9'
    client = make(peer)
    monkeypatch.setattr(deps, 'READ_LIMIT', 1)
    app.state.ctx.limiter.check('read', peer, 1)
    for forged in ['198.51.100.8', '198.51.100.9']:
        assert client.get('/ebook/api/v1/books', headers={'X-Forwarded-For': forged}).status_code == 429


def test_forwarded_allow_ips_override_is_consumed_by_uvicorn(proxy_stack):
    _, book_id, make = proxy_stack
    override = '127.0.0.1,::1,172.24.8.1/32'
    headers = {'Origin': 'https://navydev.top', 'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '203.0.113.9'}
    assert make('172.24.8.1', override).post(f'/ebook/api/v1/books/{book_id}/open', headers=headers).status_code == 200
    assert make(GATEWAY, override).post(f'/ebook/api/v1/books/{book_id}/open', headers=headers).status_code == 403


def test_custom_gateway_updates_default_trust(proxy_stack):
    _, book_id, make = proxy_stack
    gateway = '172.24.8.1'
    assert compose_default_trust(gateway) == f'127.0.0.1,::1,{gateway}/32'
    headers = {'Origin': 'https://navydev.top', 'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '203.0.113.9'}
    assert make(gateway, gateway=gateway).post(f'/ebook/api/v1/books/{book_id}/open', headers=headers).status_code == 200
    assert make(GATEWAY, gateway=gateway).post(f'/ebook/api/v1/books/{book_id}/open', headers=headers).status_code == 403


def test_compose_keeps_proxy_network_and_port_private():
    compose = COMPOSE.read_text()
    assert compose_default_trust() == '127.0.0.1,::1,172.30.81.1/32'
    assert '"127.0.0.1:8010:8010"' in compose
    assert re.search(r'networks:\s*\n\s+- lector_proxy', compose)
    assert re.search(r'lector_proxy:\s*\n\s+driver: bridge', compose)
    assert 'subnet: ${LECTOR_PROXY_SUBNET:-172.30.81.0/24}' in compose
    assert f'gateway: ${{LECTOR_PROXY_GATEWAY:-{GATEWAY}}}' in compose
