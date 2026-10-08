from __future__ import annotations

from pathlib import Path

from app import auth, llm
from app.main import app
from fastapi.testclient import TestClient


def test_modelos_endpoint_lists_downloaded_models(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(auth, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(auth, 'USERS_FILE', tmp_path / 'users.json')
    monkeypatch.setattr(auth, 'AUTH_DISABLED', False)
    auth._sessions.clear()
    auth._login_failures.clear()

    async def fake_modelos(detallado=False):
        if detallado:
            return [
                {'name': 'gemma4:e4b', 'size_human': '4.1 GB', 'capabilities': {'texto': True, 'vision': True, 'json': True}, 'warnings': []},
                {'name': 'qwen2.5vl:7b', 'size_human': '5.0 GB', 'capabilities': {'texto': True, 'vision': True, 'json': True}, 'warnings': []},
            ]
        return ['gemma4:e4b', 'qwen2.5vl:7b']

    monkeypatch.setattr(llm, 'modelos_disponibles', fake_modelos)

    with TestClient(app, base_url='http://localhost:8082') as client:
        client.post('/api/auth/setup', json={'username': 'admin', 'password': 'TipoBeta2026!'})
        r = client.get('/api/modelos')
        assert r.status_code == 200, r.text
        data = r.json()
        assert 'gemma4:e4b' in data['modelos']
        assert data['modelo_predeterminado'] in data['modelos']
        assert data['modelos_detalle'][0]['capabilities']['vision'] is True


def test_diagnostico_endpoint_returns_safe_operational_info(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(auth, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(auth, 'USERS_FILE', tmp_path / 'users.json')
    monkeypatch.setattr(auth, 'AUTH_DISABLED', False)
    auth._sessions.clear()
    auth._login_failures.clear()

    with TestClient(app, base_url='http://localhost:8082') as client:
        client.post('/api/auth/setup', json={'username': 'admin', 'password': 'TipoBeta2026!'})
        r = client.get('/api/diagnostico')
        assert r.status_code == 200, r.text
        assert r.json()['alcance_beta'] == 'monografia_moderna_impresa'
