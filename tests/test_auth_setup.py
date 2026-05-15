from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import auth
from app.main import app


def _reset_auth(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth, "AUTH_DISABLED", False)
    auth._sessions.clear()
    auth._login_failures.clear()


def test_initial_setup_creates_admin_and_sets_cookie(tmp_path: Path, monkeypatch):
    _reset_auth(tmp_path, monkeypatch)

    with TestClient(app, base_url="http://localhost:8082") as client:
        status = client.get("/api/auth/status")
        assert status.status_code == 200
        assert status.json()["setup_required"] is True

        response = client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "TipoBeta2026!"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["user"]["role"] == "admin"
        assert "tipo_session" in response.cookies
        assert (tmp_path / "tipo_auth.sqlite3").exists()

        status = client.get("/api/auth/status")
        assert status.status_code == 200
        assert status.json()["authenticated"] is True
        assert status.json()["setup_required"] is False
        assert status.json()["security"]["backend"] == "sqlite"


def test_setup_returns_clear_error_when_user_store_not_writable(tmp_path: Path, monkeypatch):
    _reset_auth(tmp_path, monkeypatch)

    def broken_db():
        raise RuntimeError("No se puede crear el usuario: el volumen local de datos no es escribible.")

    monkeypatch.setattr(auth, "_db", broken_db)

    with TestClient(app, base_url="http://localhost:8082") as client:
        response = client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "TipoBeta2026!"},
        )
        assert response.status_code == 500
        assert "volumen local de datos" in response.json()["detail"]


def test_login_lock_after_repeated_failures(tmp_path: Path, monkeypatch):
    _reset_auth(tmp_path, monkeypatch)
    monkeypatch.setattr(auth, "LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(auth, "LOGIN_LOCK_SECONDS", 60)

    with TestClient(app, base_url="http://localhost:8082") as client:
        client.post("/api/auth/setup", json={"username": "admin", "password": "TipoBeta2026!"})
        client.post("/api/auth/logout")
        for _ in range(3):
            r = client.post("/api/auth/login", json={"username": "admin", "password": "mal"})
            assert r.status_code in {401, 429}
        locked = client.post("/api/auth/login", json={"username": "admin", "password": "mal"})
        assert locked.status_code == 429
