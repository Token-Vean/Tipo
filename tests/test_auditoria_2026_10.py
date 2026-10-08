"""Tests de regresión de la auditoría de seguridad de octubre de 2026.

Cada test cubre uno de los hallazgos corregidos; el número entre corchetes
remite a la lista del informe (1-11) o a "extra" para lo detectado aparte.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import threading
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import api, auth, exportadores, llm, lotes
from app import router as router_mod
from app.main import app
from app.router import ErrorValidacion
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

BASE = "http://localhost:8082"
ADMIN = {"username": "admin", "password": "TipoBeta2026!"}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _preparar(tmp_path: Path, monkeypatch) -> None:
    """Aísla auth y lotes en tmp_path (mismo fichero SQLite, como en producción)."""
    monkeypatch.setattr(auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth, "AUTH_DISABLED", False)
    monkeypatch.setattr(lotes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lotes, "LOTES_DIR", tmp_path / "batches")
    monkeypatch.setattr(lotes, "DB_PATH", tmp_path / auth.SQLITE_FILE_NAME)
    auth._sessions.clear()
    auth._login_failures.clear()


def _vaciar_cola_lotes() -> None:
    while not lotes._cola.empty():
        lotes._cola.get_nowait()


def _cabeceras(client: TestClient) -> dict[str, str]:
    token = client.get("/api/csrf").json()["token"]
    return {"X-CSRF-Token": token, "Origin": BASE}


def _insertar_lote(username: str, estado: str = "finalizado", finalizado_en: str | None = None) -> str:
    """Crea un lote mínimo directamente en BD y en disco."""
    lote_id = hashlib.sha256(f"{username}{estado}{finalizado_en}".encode()).hexdigest()[:16]
    item_dir = lotes.LOTES_DIR / lote_id / "item0001"
    item_dir.mkdir(parents=True, exist_ok=True)
    (item_dir / "000__original.pdf").write_bytes(b"%PDF-1.4 original")
    (item_dir / "result.json").write_text("{}", encoding="utf-8")
    ahora = lotes._ahora()
    with lotes._db() as conn:
        conn.execute(
            "INSERT INTO lotes (id, username, creado_en, finalizado_en, estado, norma, modo, "
            "idioma_salida, modelo, incognito, agrupacion, total_items) "
            "VALUES (?, ?, ?, ?, ?, 'marc21-monografias', 'esencial', 'es', 'm', 0, "
            "'un_libro_por_fichero', 1)",
            (lote_id, username, finalizado_en or ahora, finalizado_en, estado),
        )
        conn.execute(
            "INSERT INTO lote_items (id, lote_id, orden, nombres_archivos, estado, ruta_entrada) "
            "VALUES (?, ?, 0, '[]', 'listo', ?)",
            (f"it{lote_id[:10]}", lote_id, str(item_dir)),
        )
    return lote_id


def _existe_lote(lote_id: str) -> bool:
    with lotes._db() as conn:
        fila = conn.execute("SELECT 1 FROM lotes WHERE id = ?", (lote_id,)).fetchone()
    return bool(fila) or (lotes.LOTES_DIR / lote_id).exists()


# ---------------------------------------------------------------------------
# [7] Límite de cuerpo en rutas públicas
# ---------------------------------------------------------------------------

def test_login_rechaza_cuerpo_enorme_por_content_length(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    cuerpo = b'{"username":"a","password":"' + b"x" * (api.MAX_AUTH_BODY_BYTES + 10) + b'"}'
    with TestClient(app, base_url=BASE) as client:
        r = client.post("/api/auth/login", content=cuerpo, headers={"Content-Type": "application/json"})
    assert r.status_code == 413, r.text


def test_login_rechaza_cuerpo_enorme_sin_content_length(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)

    def trozos():
        yield b'{"username":"a","password":"'
        for _ in range(8):
            yield b"x" * 4096
        yield b'"}'

    with TestClient(app, base_url=BASE) as client:
        r = client.post("/api/auth/login", content=trozos(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413, r.text


def test_limite_por_defecto_cubre_rutas_no_listadas():
    assert api.LimiteCuerpoPeticion._limite_para("POST", "/api/auth/login") == (api.MAX_AUTH_BODY_BYTES, False)
    assert api.LimiteCuerpoPeticion._limite_para("POST", "/api/lote") == (api.MAX_LOTE_BODY_BYTES, True)
    assert api.LimiteCuerpoPeticion._limite_para("POST", "/api/lote/x/cancelar") == (api.MAX_BODY_BYTES_DEFECTO, False)
    assert api.LimiteCuerpoPeticion._limite_para("GET", "/api/estado") is None


# ---------------------------------------------------------------------------
# [6] + extra: throttling por cliente y coste constante de PBKDF2
# ---------------------------------------------------------------------------

def test_rotar_nombres_de_usuario_no_evita_el_bloqueo(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(auth, "LOGIN_MAX_ATTEMPTS_IP", 4)
    with TestClient(app, base_url=BASE) as client:
        client.post("/api/auth/setup", json=ADMIN)
        client.post("/api/auth/logout")
        for i in range(4):
            r = client.post("/api/auth/login", json={"username": f"inexistente{i}", "password": "mal"})
            assert r.status_code == 401, r.text
        bloqueado = client.post("/api/auth/login", json={"username": "otro_nombre", "password": "mal"})
        assert bloqueado.status_code == 429, bloqueado.text
        # El bloqueo es del cliente: tampoco deja probar al usuario real.
        tambien = client.post("/api/auth/login", json=ADMIN)
        assert tambien.status_code == 429


def test_usuario_inexistente_cuesta_un_solo_pbkdf2(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    auth._hash_ficticio()  # el hash ficticio se calcula una vez por proceso
    llamadas = {"n": 0}
    original = auth.hashlib.pbkdf2_hmac

    def contar(*args, **kwargs):
        llamadas["n"] += 1
        return original(*args, **kwargs)

    with TestClient(app, base_url=BASE) as client:
        client.post("/api/auth/setup", json=ADMIN)
        client.post("/api/auth/logout")
        monkeypatch.setattr(auth.hashlib, "pbkdf2_hmac", contar)

        llamadas["n"] = 0
        r = client.post("/api/auth/login", json={"username": "nadie", "password": "mal"})
        assert r.status_code == 401
        coste_inexistente = llamadas["n"]

        llamadas["n"] = 0
        r = client.post("/api/auth/login", json={"username": "admin", "password": "mal"})
        assert r.status_code == 401
        coste_existente = llamadas["n"]

    assert coste_inexistente == coste_existente == 1


# ---------------------------------------------------------------------------
# [10] Setup y login no aceptan peticiones de otra web
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cabeceras",
    [
        {"Origin": "https://malicioso.example"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Referer": "https://malicioso.example/pagina"},
        {"Origin": "http://localhost:9999"},
    ],
)
def test_setup_rechaza_peticiones_entre_sitios(tmp_path: Path, monkeypatch, cabeceras):
    _preparar(tmp_path, monkeypatch)
    with TestClient(app, base_url=BASE) as client:
        r = client.post("/api/auth/setup", json=ADMIN, headers=cabeceras)
        assert r.status_code == 403, r.text
        assert client.get("/api/auth/status").json()["setup_required"] is True
        # Desde la propia aplicación sigue funcionando.
        ok = client.post(
            "/api/auth/setup", json=ADMIN,
            headers={"Origin": BASE, "Sec-Fetch-Site": "same-origin"},
        )
        assert ok.status_code == 200, ok.text


# ---------------------------------------------------------------------------
# [8] Borrar o recrear un usuario no deja lotes heredables
# ---------------------------------------------------------------------------

def test_borrar_usuario_elimina_sus_lotes(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    with TestClient(app, base_url=BASE) as client:
        client.post("/api/auth/setup", json=ADMIN)
        h = _cabeceras(client)
        r = client.post("/api/auth/usuarios", json={"username": "becario", "password": "TipoBeta2026?", "role": "user"}, headers=h)
        assert r.status_code == 200, r.text
        lote_id = _insertar_lote("becario")
        lote_ajeno = _insertar_lote("admin")
        r = client.delete("/api/auth/usuarios/becario", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["lotes_borrados"] == 1
    assert not _existe_lote(lote_id)
    assert _existe_lote(lote_ajeno)


def test_recrear_nombre_no_hereda_lotes_huerfanos(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    with TestClient(app, base_url=BASE) as client:
        client.post("/api/auth/setup", json=ADMIN)
        h = _cabeceras(client)
        # Restos de un "becario" borrado con una versión anterior.
        huerfano = _insertar_lote("becario")
        r = client.post("/api/auth/usuarios", json={"username": "becario", "password": "TipoBeta2026?", "role": "user"}, headers=h)
        assert r.status_code == 200, r.text
    assert not _existe_lote(huerfano)


# ---------------------------------------------------------------------------
# [3] Cuota, retención y originales en incógnito
# ---------------------------------------------------------------------------

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


def test_cuota_por_usuario_rechaza_y_no_deja_restos(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(lotes, "MAX_BYTES_USUARIO", 3000)
    _crear_lote([("a.pdf", b"a" * 2000)])
    with pytest.raises(ValueError, match="espacio máximo"):
        _crear_lote([("b.pdf", b"b" * 2000)])
    # Solo queda el primer lote en disco.
    assert len(list((tmp_path / "batches").iterdir())) == 1


def test_limite_de_lote_sigue_vigente_con_subida_por_bloques(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(lotes, "MAX_BYTES_LOTE", 1500)
    with pytest.raises(ValueError, match="tamaño máximo"):
        _crear_lote([("a.pdf", b"a" * 1000), ("b.pdf", b"b" * 1000)])
    assert not any((tmp_path / "batches").iterdir())


def test_incognito_borra_originales_al_terminar(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    lote_id = _crear_lote([("libro.pdf", b"%PDF-1.4 secreto")], incognito=True)
    with lotes._db() as conn:
        item = conn.execute("SELECT id, ruta_entrada FROM lote_items WHERE lote_id = ?", (lote_id,)).fetchone()
        conn.execute("UPDATE lote_items SET estado = 'listo' WHERE id = ?", (item["id"],))
    item_dir = Path(item["ruta_entrada"])
    (item_dir / "result.json").write_text("{}", encoding="utf-8")

    lotes.limpiar_originales_si_procede(item["id"])

    assert [p.name for p in item_dir.iterdir()] == ["result.json"]


def test_modo_normal_conserva_originales_por_defecto(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    lote_id = _crear_lote([("libro.pdf", b"%PDF-1.4 normal")])
    with lotes._db() as conn:
        item = conn.execute("SELECT id, ruta_entrada FROM lote_items WHERE lote_id = ?", (lote_id,)).fetchone()
        conn.execute("UPDATE lote_items SET estado = 'listo' WHERE id = ?", (item["id"],))
    lotes.limpiar_originales_si_procede(item["id"])
    assert any(p.name.endswith("libro.pdf") for p in Path(item["ruta_entrada"]).iterdir())


def test_retencion_borra_solo_lotes_terminados_antiguos(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(lotes, "RETENCION_DIAS", 30)
    # Mismo formato y zona (hora local, sin tz) que usa lotes._ahora().
    viejo = (datetime.fromisoformat(lotes._ahora()) - timedelta(days=40)).isoformat(timespec="seconds")
    antiguo = _insertar_lote("admin", "finalizado", viejo)
    reciente = _insertar_lote("admin", "finalizado")
    pendiente_viejo = _insertar_lote("admin", "pendiente", viejo)
    assert lotes.purgar_lotes_caducados() == 1
    assert not _existe_lote(antiguo)
    assert _existe_lote(reciente)
    assert _existe_lote(pendiente_viejo)


# ---------------------------------------------------------------------------
# [5] Presupuesto global de imágenes
# ---------------------------------------------------------------------------

def _doc_con_imagenes(*tamanos: int):
    return SimpleNamespace(entrada=SimpleNamespace(imagenes=[b"\0" * t for t in tamanos]))


def test_presupuesto_de_imagenes_se_suma_entre_ficheros(monkeypatch):
    monkeypatch.setattr(api, "MAX_BYTES_IMAGENES_PETICION", 1000)
    acumulado = api.comprobar_presupuesto_imagenes(0, _doc_con_imagenes(400, 300))
    assert acumulado == 700
    with pytest.raises(ErrorValidacion, match="demasiadas imágenes"):
        api.comprobar_presupuesto_imagenes(acumulado, _doc_con_imagenes(400))


# ---------------------------------------------------------------------------
# [4] El parsing de /api/describir no se ejecuta en el hilo del event loop
# ---------------------------------------------------------------------------

def test_describir_procesa_fuera_del_event_loop(tmp_path: Path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    hilos: dict[str, int] = {}

    async def modelos_falsos(detallado=False):
        hilos["loop"] = threading.get_ident()
        return ["gemma4:e4b"]

    def procesar_falso(contenido, nombre):
        hilos["parser"] = threading.get_ident()
        raise ErrorValidacion("documento de prueba")

    monkeypatch.setattr(llm, "modelos_disponibles", modelos_falsos)
    monkeypatch.setattr(router_mod, "procesar", procesar_falso)

    with TestClient(app, base_url=BASE) as client:
        client.post("/api/auth/setup", json=ADMIN)
        r = client.post(
            "/api/describir",
            files={"ficheros": ("portada.jpg", b"\xff\xd8\xff", "image/jpeg")},
            data={"modelo": "gemma4:e4b"},
            headers=_cabeceras(client),
        )
    assert r.status_code == 400, r.text
    assert "loop" in hilos and "parser" in hilos
    assert hilos["parser"] != hilos["loop"]


# ---------------------------------------------------------------------------
# [11] MARC21 en texto: sin campos ni subcampos inyectados
# ---------------------------------------------------------------------------

def test_marc_texto_no_admite_campos_ni_subcampos_inyectados():
    campos = [
        {"clave": "titulo_principal", "valor": "Historia de Getafe $x Subcampo falso"},
        {"clave": "mencion_responsabilidad", "valor": "Juan Pérez\n650 #0 $a Materia falsa"},
        {"clave": "isbn", "valor": ["978-84-376-0494-7", "x\r\n$z y"]},
    ]
    texto = exportadores.marc21_a_texto_plano(exportadores.generar_marc21_texto(campos))
    lineas = texto.splitlines()
    assert not any(linea.startswith("650") for linea in lineas)
    assert " $x " not in texto and " $z " not in texto
    assert "{dollar}x Subcampo falso" in texto
    # Los subcampos legítimos siguen ahí.
    assert any(linea.startswith("245 1 0 $a Historia de Getafe") for linea in lineas)
