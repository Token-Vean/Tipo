"""Regresiones de integración de la revisión de noviembre de 2026
(Tipo 0.3.1-beta.1): permisos, sesiones, modo incógnito, lotes y SQLite.
"""

from __future__ import annotations

import asyncio
import io
import sqlite3
import time
import zipfile
from pathlib import Path

import pytest
from app import api, auth, lotes
from app.main import app
from app.router import ErrorValidacion
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

BASE = "http://localhost:8769"
ADMIN = {"username": "admin", "password": "TipoBeta2026!"}
USUARIO = {"username": "catalogador", "password": "TipoBeta2026?"}


def _preparar(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth, "AUTH_DISABLED", False)
    monkeypatch.setattr(lotes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lotes, "LOTES_DIR", tmp_path / "batches")
    monkeypatch.setattr(lotes, "DB_PATH", tmp_path / auth.SQLITE_FILE_NAME)
    auth._sessions.clear()
    auth._login_failures.clear()


def _cabeceras(client: TestClient) -> dict[str, str]:
    token = client.get("/api/csrf").json()["token"]
    return {"X-CSRF-Token": token, "Origin": BASE}


def _vaciar_cola_lotes() -> None:
    while not lotes._cola.empty():
        lotes._cola.get_nowait()


def _crear_lote(ficheros: list[tuple[str, bytes]], **kw) -> str:
    uploads = [UploadFile(file=io.BytesIO(datos), filename=nombre) for nombre, datos in ficheros]
    parametros = {
        "agrupacion": "un_libro_por_fichero", "norma": "marc21-monografias", "modo": "esencial",
        "campos": None, "idioma_salida": "es", "modelo": "m", "incognito": False,
        "etiquetas": None, "username": "admin",
    }
    parametros.update(kw)
    try:
        return asyncio.run(lotes.crear_lote(ficheros=uploads, **parametros))
    finally:
        _vaciar_cola_lotes()


# ---------------------------------------------------------------------------
# Apagado solo para administradores
# ---------------------------------------------------------------------------

def test_usuario_no_admin_no_puede_apagar(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    llamadas = []
    monkeypatch.setattr(api, "_apagar_proceso_app", lambda: llamadas.append(1))
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 200
        alta = client.post("/api/auth/usuarios", json={**USUARIO, "role": "user"}, headers=_cabeceras(client))
        assert alta.status_code == 200, alta.text
        client.post("/api/auth/logout")
        assert client.post("/api/auth/login", json=USUARIO).status_code == 200
        r = client.post("/api/apagar", headers=_cabeceras(client))
    assert r.status_code == 403, r.text
    assert llamadas == []


# ---------------------------------------------------------------------------
# Sesiones
# ---------------------------------------------------------------------------

def test_login_revoca_el_token_anterior_del_navegador(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 200
        anterior = client.cookies.get(auth.COOKIE_NAME)
        assert anterior in auth._sessions
        assert client.post("/api/auth/login", json=ADMIN).status_code == 200
        nuevo = client.cookies.get(auth.COOKIE_NAME)
    assert nuevo != anterior
    assert anterior not in auth._sessions
    assert nuevo in auth._sessions


def test_sesion_con_tope_absoluto(monkeypatch):
    auth._sessions.clear()
    monkeypatch.setattr(auth, "SESSION_MAX_SECONDS", 60)
    ahora = time.time()
    auth._sessions["vieja"] = {"username": "a", "created": ahora - 120, "expires": ahora + 3600}
    auth._sessions["nueva"] = {"username": "a", "created": ahora, "expires": ahora + 3600}
    auth._purgar_sesiones()
    assert "vieja" not in auth._sessions
    assert "nueva" in auth._sessions
    auth._sessions.clear()


# ---------------------------------------------------------------------------
# SQLite: conexiones cerradas y retención de eventos
# ---------------------------------------------------------------------------

def test_db_cierra_la_conexion(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    with auth._db() as conn:
        conn.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
    with lotes._db() as conn_lotes:
        conn_lotes.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        conn_lotes.execute("SELECT 1")


def test_purgar_eventos_antiguos(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(auth, "EVENTOS_RETENCION_DIAS", 90)
    with auth._db() as conn:
        conn.execute(
            "INSERT INTO security_events(created_at, event_type) VALUES (?, ?)",
            ("2020-01-01T00:00:00Z", "login_failed"),
        )
        auth._record_event(conn, "login_failed", target="reciente")
    assert auth.purgar_eventos_antiguos() == 1
    with auth._db() as conn:
        restantes = [r["target"] for r in conn.execute("SELECT target FROM security_events")]
    assert restantes == ["reciente"]


# ---------------------------------------------------------------------------
# Modo incógnito
# ---------------------------------------------------------------------------

def test_anonimizar_documento_quita_nombres_y_huellas():
    documento = {
        "nombre": "expediente-garcia.pdf, dni.jpg",
        "archivos": [
            {"etiqueta": "portada", "nombre": "expediente-garcia.pdf", "sha256": "a" * 64},
            {"etiqueta": "verso", "nombre": "dni.jpg", "sha256": "b" * 64},
        ],
        "cobertura_zonas": [
            {"etiqueta": "portada", "archivo": "expediente-garcia.pdf"},
            {"etiqueta": "verso", "archivo": "dni.jpg"},
        ],
    }
    anon = api.anonimizar_documento(documento)
    texto = repr(anon)
    assert "garcia" not in texto and "dni" not in texto
    assert "a" * 64 not in texto
    assert [a["nombre"] for a in anon["archivos"]] == ["archivo_1", "archivo_2"]
    assert [c["archivo"] for c in anon["cobertura_zonas"]] == ["archivo_1", "archivo_2"]
    assert [a["etiqueta"] for a in anon["archivos"]] == ["portada", "verso"]
    # El original no se modifica.
    assert documento["archivos"][0]["nombre"] == "expediente-garcia.pdf"


# ---------------------------------------------------------------------------
# Lotes: originales, ZIP cifrado y plazo visible
# ---------------------------------------------------------------------------

def test_originales_se_borran_por_defecto_al_terminar(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(lotes, "CONSERVAR_ORIGINALES", False)
    lote_id = _crear_lote([("libro.pdf", b"%PDF-1.4 normal")])
    with lotes._db() as conn:
        item = conn.execute("SELECT id, ruta_entrada FROM lote_items WHERE lote_id = ?", (lote_id,)).fetchone()
        conn.execute("UPDATE lote_items SET estado = 'listo' WHERE id = ?", (item["id"],))
    item_dir = Path(item["ruta_entrada"])
    (item_dir / "result.json").write_text("{}", encoding="utf-8")
    lotes.limpiar_originales_si_procede(item["id"])
    assert [p.name for p in item_dir.iterdir()] == ["result.json"]


def _zip_marcado_como_cifrado() -> bytes:
    """ZIP con el bit de cifrado activo (zipfile no sabe escribirlos: se
    marca a mano en la cabecera local y en el directorio central)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("portada.jpg", b"datos")
    datos = bytearray(buffer.getvalue())
    local = datos.find(b"PK\x03\x04")
    central = datos.find(b"PK\x01\x02")
    datos[local + 6] |= 0x1
    datos[central + 8] |= 0x1
    return bytes(datos)


def test_zip_cifrado_es_error_de_validacion(tmp_path: Path):
    with pytest.raises(ErrorValidacion, match="cifrado"):
        lotes._extraer_zip_libro(_zip_marcado_como_cifrado(), tmp_path / "destino")


def test_detalle_de_lote_informa_del_plazo_de_conservacion(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(lotes, "RETENCION_DIAS", 7)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 200
        lote_id = _crear_lote([("libro.pdf", b"%PDF-1.4 normal")])
        r = client.get(f"/api/lote/{lote_id}")
    assert r.status_code == 200, r.text
    assert r.json()["almacenamiento"] == {"retencion_dias": 7, "conserva_originales": lotes.CONSERVAR_ORIGINALES}


# ---------------------------------------------------------------------------
# /api/estado identifica a la aplicación
# ---------------------------------------------------------------------------

def test_estado_identifica_a_tipo(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    with TestClient(app, base_url=BASE) as client:
        datos = client.get("/api/estado").json()
    assert datos["aplicacion"] == "Tipo"
