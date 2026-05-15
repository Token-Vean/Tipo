from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import auth
from app.main import app


def _csrf(client: TestClient) -> str:
    return client.get('/api/csrf').json()['token']


def _reset_auth(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(auth, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(auth, 'USERS_FILE', tmp_path / 'users.json')
    monkeypatch.setattr(auth, 'AUTH_DISABLED', False)
    auth._sessions.clear()
    auth._login_failures.clear()


def test_user_can_change_own_password(tmp_path: Path, monkeypatch):
    _reset_auth(tmp_path, monkeypatch)

    with TestClient(app, base_url='http://localhost:8082') as client:
        client.post('/api/auth/setup', json={'username': 'admin', 'password': 'TipoBeta2026!'})
        token = _csrf(client)
        r = client.post(
            '/api/auth/password',
            json={'current_password': 'TipoBeta2026!', 'new_password': 'TipoBeta2026!!'},
            headers={'X-CSRF-Token': token, 'Origin': 'http://localhost:8082'},
        )
        assert r.status_code == 200, r.text
        client.post('/api/auth/logout')
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'TipoBeta2026!!'})
        assert login.status_code == 200, login.text


def test_admin_can_create_reset_disable_and_delete_user(tmp_path: Path, monkeypatch):
    _reset_auth(tmp_path, monkeypatch)

    with TestClient(app, base_url='http://localhost:8082') as client:
        client.post('/api/auth/setup', json={'username': 'admin', 'password': 'TipoBeta2026!'})
        token = _csrf(client)
        headers = {'X-CSRF-Token': token, 'Origin': 'http://localhost:8082'}

        create = client.post('/api/auth/usuarios', json={'username': 'catalogador', 'password': 'TipoBeta2026?', 'role': 'user'}, headers=headers)
        assert create.status_code == 200, create.text

        reset = client.post('/api/auth/usuarios/catalogador/password', json={'password': 'TipoBeta2026!!'}, headers=headers)
        assert reset.status_code == 200, reset.text

        disable = client.post('/api/auth/usuarios/catalogador/estado', json={'disabled': True}, headers=headers)
        assert disable.status_code == 200, disable.text

        delete = client.delete('/api/auth/usuarios/catalogador', headers=headers)
        assert delete.status_code == 200, delete.text


def test_legacy_users_json_is_migrated_to_sqlite(tmp_path: Path, monkeypatch):
    _reset_auth(tmp_path, monkeypatch)
    legacy_hash = auth._hash_password('TipoBeta2026!')
    (tmp_path / 'users.json').write_text(
        '{"version":1,"users":{"admin":{"password_hash":"%s","role":"admin","created_at":"2026-01-01T00:00:00Z","disabled":false}}}' % legacy_hash,
        encoding='utf-8',
    )
    assert auth.hay_usuarios() is True
    assert (tmp_path / 'tipo_auth.sqlite3').exists()
    assert (tmp_path / 'users.json.migrated').exists()
