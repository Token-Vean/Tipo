"""Optimizaciones de rendimiento de Tipo 0.3.1-beta.1.

1. Solo se extrae el texto de las páginas de zona del PDF.
2. num_ctx se ajusta al tamaño de la petición y el documento se recorta
   (principio y final) en lugar de dejar que Ollama descarte las instrucciones.
3. Salida estructurada: esquema JSON en `format`, con reserva a "json".
4. Imágenes para el modelo en JPEG de lado máximo acotado y con la
   orientación EXIF aplicada.
5. Esquema SQLite preparado una sola vez y caché breve de usuario.

No necesitan levantar la aplicación ni un Ollama real.
"""

from __future__ import annotations

import asyncio
import io
import json
import sqlite3
import time
from pathlib import Path

import pytest
from app import auth, extractor, llm, lotes, zonas
from app import router as router_mod

ROOT = Path(__file__).resolve().parents[1]
ESQUEMA = ROOT / "schemas" / "datos-bibliograficos-monografia.yaml"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def pdf_con_paginas(textos: list[str]) -> bytes:
    """PDF mínimo, una línea de texto por página (Helvetica)."""
    objetos: list[bytes] = []
    n = len(textos)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objetos.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, texto in enumerate(textos):
        contenido = f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1")
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 595] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode()
        )
        objetos.append(
            b"<< /Length %d >>\nstream\n" % len(contenido) + contenido + b"\nendstream"
        )
    salida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, obj in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida += f"{num} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        salida += f"{off:010d} 00000 n \n".encode()
    salida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(salida)


def _respuesta_vacia(esquema: extractor.Esquema) -> str:
    return json.dumps({
        "campos": {
            el.clave: {"valor": None, "confianza": None, "evidencia": None, "zona": None}
            for el in esquema.extraibles()
        }
    })


# ---------------------------------------------------------------------------
# 1. Extracción solo de las páginas de zona
# ---------------------------------------------------------------------------

def test_indices_zonas_coinciden_con_la_segmentacion():
    prelim, finales = zonas.indices_zonas(40)
    assert prelim == list(range(zonas.PAGINAS_PRELIMINARES))
    assert finales == list(range(40 - zonas.PAGINAS_FINALES, 40))
    # Libros cortos: sin solapamiento.
    p, f = zonas.indices_zonas(5)
    assert not set(p) & set(f)
    assert sorted(p + f) == list(range(5))
    assert zonas.indices_zonas(0) == ([], [])


def test_pdf_solo_extrae_texto_de_las_zonas():
    total = 40
    pdf = pdf_con_paginas([f"PAGINA {i + 1}" for i in range(total)])
    paginas = router_mod._extraer_texto_pdf_por_pagina(pdf)
    assert len(paginas) == total
    prelim, finales = zonas.indices_zonas(total)
    leidas = set(prelim + finales)
    for i, texto in enumerate(paginas):
        if i in leidas:
            assert f"PAGINA {i + 1}" in texto
        else:
            assert texto == "", f"la página {i + 1} no es de zona y no debía leerse"


# ---------------------------------------------------------------------------
# 4. Imágenes para el modelo
# ---------------------------------------------------------------------------

def _png(ancho: int, alto: int, modo: str = "RGB", exif_orientacion: int | None = None) -> bytes:
    from PIL import Image

    img = Image.new(modo, (ancho, alto), color=(200, 30, 30, 255)[: len(modo)] if modo != "L" else 128)
    buf = io.BytesIO()
    if exif_orientacion is not None:
        exif = Image.Exif()
        exif[0x0112] = exif_orientacion
        img.save(buf, format="JPEG", exif=exif.tobytes())
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


def test_imagen_grande_se_reduce_y_se_codifica_en_jpeg():
    from PIL import Image

    salida = router_mod._validar_imagen(_png(4000, 3000))
    assert salida[:3] == b"\xff\xd8\xff"
    with Image.open(io.BytesIO(salida)) as img:
        assert img.format == "JPEG"
        assert max(img.size) == router_mod.VISION_LADO_MAX


def test_imagen_con_transparencia_pasa_a_rgb():
    from PIL import Image

    salida = router_mod._validar_imagen(_png(300, 200, modo="RGBA"))
    with Image.open(io.BytesIO(salida)) as img:
        assert img.format == "JPEG" and img.mode == "RGB"
        assert img.size == (300, 200)


def test_imagen_respeta_la_orientacion_exif_y_no_conserva_exif():
    from PIL import Image

    # Foto apaisada con orientación 6 (girar 90°): debe llegar vertical.
    salida = router_mod._validar_imagen(_png(2000, 1500, exif_orientacion=6))
    with Image.open(io.BytesIO(salida)) as img:
        ancho, alto = img.size
        assert alto > ancho
        assert max(img.size) == router_mod.VISION_LADO_MAX
        assert 0x0112 not in img.getexif()


def test_escala_de_render_no_supera_el_lado_maximo():
    # A4 en puntos: con la escala 2 serían 1190x1684 px.
    escala = router_mod._escala_render(595, 842)
    assert 842 * escala <= router_mod.VISION_LADO_MAX + 1
    # Páginas pequeñas no se amplían por encima de la escala base.
    assert router_mod._escala_render(200, 300) == router_mod.ESCALA_RENDER_PDF


# ---------------------------------------------------------------------------
# 2. Presupuesto de contexto
# ---------------------------------------------------------------------------

def test_num_ctx_por_tramos_y_nunca_por_encima_del_maximo(monkeypatch):
    monkeypatch.setattr(llm, "NUM_CTX", 32768)
    pequeno = llm.num_ctx_para(20_000)
    assert pequeno in llm.TRAMOS_NUM_CTX and pequeno < 32768
    assert llm.tokens_necesarios(20_000) <= pequeno
    # Peticiones parecidas caen en el mismo tramo (sin recargar el modelo).
    assert llm.num_ctx_para(20_500) == pequeno
    # Las imágenes cuentan.
    assert llm.num_ctx_para(20_000, imagenes=10) > pequeno
    # Nunca se supera OLLAMA_NUM_CTX, aunque no quepa.
    assert llm.num_ctx_para(10_000_000) == 32768
    monkeypatch.setattr(llm, "NUM_CTX", 20000)
    assert llm.num_ctx_para(1000) == 16384
    assert llm.num_ctx_para(40_000) == 20000


def test_caracteres_disponibles_respetan_la_ventana(monkeypatch):
    monkeypatch.setattr(llm, "NUM_CTX", 32768)
    resto = 35_000
    disponibles = llm.caracteres_documento_disponibles(resto)
    assert llm.tokens_necesarios(resto + disponibles) <= 32768 + 1
    # Siempre queda un mínimo de documento, aunque el resto sea enorme.
    assert llm.caracteres_documento_disponibles(10_000_000) == llm.MIN_CARACTERES_DOCUMENTO


def test_ajustar_documento_conserva_principio_y_final():
    lineas = [f"línea {i:04d} " + "x" * 50 for i in range(2000)]
    documento = "\n".join(lineas)
    recortado, omitidos = extractor.ajustar_documento_a_contexto(documento, 20_000)
    assert len(recortado) <= 20_000
    assert omitidos > 0
    assert recortado.startswith("línea 0000")
    assert recortado.endswith(lineas[-1])
    assert f"{omitidos} caracteres" in recortado
    # La marca no imita cabeceras de zona ni delimitadores.
    assert "=====" not in recortado and "<<<" not in recortado
    # Un documento que cabe no se toca.
    assert extractor.ajustar_documento_a_contexto("corto", 100) == ("corto", 0)


@pytest.mark.parametrize("diagnostico, esperado", [
    ({"num_ctx": 16384, "prompt_eval_count": 16384, "eval_count": 10}, "prompt_truncado"),
    ({"num_ctx": 16384, "prompt_eval_count": 16000, "eval_count": 900}, "contexto_agotado"),
    ({"num_ctx": 32768, "num_predict": 8192, "prompt_eval_count": 9000,
      "eval_count": 8192, "done_reason": "length"}, "limite_salida"),
    ({"num_ctx": 32768, "prompt_eval_count": 9000, "eval_count": 900, "done_reason": "stop"}, None),
    ({}, None),
    (None, None),
])
def test_evaluar_contexto(diagnostico, esperado):
    assert llm.evaluar_contexto(diagnostico) == esperado


def _instalar_generar_falso(monkeypatch, respuesta: str, diagnostico_falso: dict | None = None):
    llamadas: list[dict] = []

    async def falso(**kwargs):
        llamadas.append(kwargs)
        if kwargs.get("diagnostico") is not None and diagnostico_falso:
            kwargs["diagnostico"].update(diagnostico_falso)
        return respuesta

    monkeypatch.setattr(llm, "generar", falso)
    monkeypatch.setattr(extractor, "cargar_ejemplos", lambda *a, **k: [])
    return llamadas


def test_extraer_recorta_el_documento_que_no_cabe(monkeypatch):
    monkeypatch.setattr(llm, "NUM_CTX", 32768)
    esquema = extractor.cargar_esquema(ESQUEMA)
    llamadas = _instalar_generar_falso(monkeypatch, _respuesta_vacia(esquema))
    texto = "PORTADA Título del libro\n" + ("relleno del cuerpo\n" * 20_000) + "COLOFÓN Imprenta final"
    entrada = extractor.Entrada(texto=texto)

    propuesta = asyncio.run(extractor.extraer(entrada, esquema, "gemma4:e2b"))

    assert len(llamadas) == 1
    llamada = llamadas[0]
    prompt = llamada["prompt"]
    assert llm.tokens_necesarios(len(prompt)) <= llamada["num_ctx"] <= 32768
    # Se conservan las instrucciones (principio del prompt), la portada y el colofón.
    assert "PORTADA Título del libro" in prompt and "COLOFÓN Imprenta final" in prompt
    assert prompt.rstrip().endswith("<<<DOCUMENTO_FIN>>>")
    assert any("ventana de contexto" in a for a in propuesta.advertencias)
    # El texto completo sigue disponible para localizar evidencias.
    assert entrada.texto == texto
    # Salida estructurada con el esquema de los campos.
    assert isinstance(llamada["formato_json"], dict)


def test_extraer_documento_pequeno_usa_un_tramo_menor(monkeypatch):
    monkeypatch.setattr(llm, "NUM_CTX", 65536)
    esquema = extractor.cargar_esquema(ESQUEMA)
    llamadas = _instalar_generar_falso(monkeypatch, _respuesta_vacia(esquema))
    propuesta = asyncio.run(
        extractor.extraer(extractor.Entrada(texto="Portada breve"), esquema, "gemma4:e2b")
    )
    assert llamadas[0]["num_ctx"] < 65536
    assert not any("ventana de contexto" in a for a in propuesta.advertencias)


def test_extraer_avisa_si_ollama_trunco_el_prompt(monkeypatch):
    esquema = extractor.cargar_esquema(ESQUEMA)
    _instalar_generar_falso(
        monkeypatch, _respuesta_vacia(esquema),
        {"num_ctx": 16384, "prompt_eval_count": 16384, "eval_count": 5},
    )
    propuesta = asyncio.run(
        extractor.extraer(extractor.Entrada(texto="Portada"), esquema, "gemma4:e2b")
    )
    assert any("descartó parte de las instrucciones" in a for a in propuesta.advertencias)


def test_reintento_usa_el_mismo_num_ctx(monkeypatch):
    esquema = extractor.cargar_esquema(ESQUEMA)
    llamadas = _instalar_generar_falso(monkeypatch, "esto no es JSON")
    asyncio.run(extractor.extraer(extractor.Entrada(texto="Portada"), esquema, "gemma4:e2b"))
    assert len(llamadas) == 2
    assert llamadas[0]["num_ctx"] == llamadas[1]["num_ctx"]
    assert llm.tokens_necesarios(len(llamadas[1]["prompt"])) <= llamadas[1]["num_ctx"]


# ---------------------------------------------------------------------------
# 3. Salida estructurada
# ---------------------------------------------------------------------------

def test_esquema_json_respuesta_cubre_todos_los_campos():
    esquema = extractor.cargar_esquema(ESQUEMA)
    extraibles = esquema.extraibles()
    salida = extractor.esquema_json_respuesta(extraibles)
    campos = salida["properties"]["campos"]
    assert salida["required"] == ["campos"] and salida["additionalProperties"] is False
    assert set(campos["required"]) == {e.clave for e in extraibles}
    assert campos["additionalProperties"] is False
    for el in extraibles:
        prop = campos["properties"][el.clave]
        assert prop["required"] == ["valor", "confianza", "evidencia", "zona"]
        tipos = prop["properties"]["valor"]["anyOf"]
        assert {"type": "null"} in tipos
        principal = tipos[0]
        if el.multiple:
            assert principal["type"] == "array"
            principal = principal["items"]
        if el.tipo == "lista" and el.valores:
            assert principal["enum"] == list(el.valores)
    # Debe poder serializarse tal cual en la petición a Ollama.
    json.dumps(salida)


def test_respuesta_conforme_al_esquema_se_parsea_sin_avisos():
    esquema = extractor.cargar_esquema(ESQUEMA)
    _, avisos = extractor.parsear_respuesta(_respuesta_vacia(esquema), esquema, None)
    assert avisos == []


class _Resp:
    def __init__(self, status_code: int, datos=None, texto: str = ""):
        self.status_code = status_code
        self._datos = datos or {}
        self.text = texto

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._datos


class _OllamaGenerar:
    def __init__(self, primera: _Resp):
        self.primera = primera
        self.posts: list[dict] = []

    def cliente(self, timeout):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        self.posts.append(dict(json))
        if len(self.posts) == 1:
            return self.primera
        return _Resp(200, {"response": "{}", "prompt_eval_count": 10, "eval_count": 2,
                           "done_reason": "stop"})


def _preparar_generar(monkeypatch, ollama: _OllamaGenerar):
    async def sin_comprobar(*a, **k):
        return None

    monkeypatch.setattr(llm, "verificar_version_ollama", sin_comprobar)
    monkeypatch.setattr(llm, "verificar_modelo_local", sin_comprobar)
    monkeypatch.setattr(llm, "cliente_local", ollama.cliente)


@pytest.mark.parametrize("primera", [
    _Resp(400, texto='{"error":"invalid format: json schema not supported"}'),
    _Resp(500, texto='{"error":"failed to load model grammar"}'),
])
def test_generar_repite_con_json_generico_si_ollama_rechaza_el_esquema(monkeypatch, primera):
    ollama = _OllamaGenerar(primera)
    _preparar_generar(monkeypatch, ollama)
    diagnostico: dict = {}
    esquema = {"type": "object", "properties": {"campos": {"type": "object"}}}
    salida = asyncio.run(llm.generar("p", "m", formato_json=esquema, num_ctx=16384,
                                     diagnostico=diagnostico))
    assert salida == "{}"
    assert [p["format"] for p in ollama.posts] == [esquema, "json"]
    assert diagnostico["num_ctx"] == 16384 and diagnostico["done_reason"] == "stop"


def test_generar_no_repite_por_errores_ajenos_al_formato(monkeypatch):
    ollama = _OllamaGenerar(_Resp(500, texto='{"error":"out of memory"}'))
    _preparar_generar(monkeypatch, ollama)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        asyncio.run(llm.generar("p", "m", formato_json={"type": "object"}))
    assert len(ollama.posts) == 1


def test_generar_limita_num_ctx_al_maximo_configurado(monkeypatch):
    monkeypatch.setattr(llm, "NUM_CTX", 16384)
    ollama = _OllamaGenerar(_Resp(200, {"response": "{}"}))
    _preparar_generar(monkeypatch, ollama)
    asyncio.run(llm.generar("p", "m", num_ctx=131072))
    assert ollama.posts[0]["options"]["num_ctx"] == 16384
    assert ollama.posts[0]["format"] == "json"


# ---------------------------------------------------------------------------
# 5. SQLite: esquema una vez y caché breve de usuario
# ---------------------------------------------------------------------------

@pytest.fixture
def datos_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth, "AUTH_DISABLED", False)
    auth._invalidar_cache_usuarios()
    yield tmp_path
    auth._invalidar_cache_usuarios()


def test_esquema_de_auth_se_prepara_una_sola_vez(datos_auth, monkeypatch):
    contador = {"n": 0}
    original = auth._ensure_schema

    def contar(conn):
        contador["n"] += 1
        original(conn)

    monkeypatch.setattr(auth, "_ensure_schema", contar)
    for _ in range(5):
        with auth._db() as conn:
            conn.execute("SELECT COUNT(*) FROM users").fetchone()
    assert contador["n"] == 1
    # Si el fichero desaparece con la aplicación en marcha, se prepara de nuevo.
    for sufijo in ("", "-wal", "-shm"):
        Path(str(auth._db_path()) + sufijo).unlink(missing_ok=True)
    with auth._db() as conn:
        conn.execute("SELECT COUNT(*) FROM users").fetchone()
    assert contador["n"] == 2
    with auth._db() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_esquema_de_lotes_se_prepara_una_sola_vez(tmp_path, monkeypatch):
    monkeypatch.setattr(lotes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lotes, "DB_PATH", tmp_path / "lotes.sqlite3")
    contador = {"n": 0}
    original = lotes._ensure_schema

    def contar(conn):
        contador["n"] += 1
        original(conn)

    monkeypatch.setattr(lotes, "_ensure_schema", contar)
    for _ in range(5):
        with lotes._db() as conn:
            conn.execute("SELECT COUNT(*) FROM lotes").fetchone()
    assert contador["n"] == 1


class _Peticion:
    def __init__(self, token: str):
        self.cookies = {auth.COOKIE_NAME: token}


def _crear_usuario(username: str, role: str = "user") -> None:
    with auth._db() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, disabled, created_at) "
            "VALUES (?, 'x', ?, 0, '2026-11-25T00:00:00')",
            (username, role),
        )


def test_cache_de_usuario_evita_consultas_repetidas(datos_auth, monkeypatch):
    _crear_usuario("ana")
    token = auth._crear_sesion("ana")
    consultas = {"n": 0}
    original = auth._get_user

    def contar(conn, username):
        consultas["n"] += 1
        return original(conn, username)

    monkeypatch.setattr(auth, "_get_user", contar)
    for _ in range(10):
        assert auth.usuario_desde_request(_Peticion(token)) == {"username": "ana", "role": "user"}
    assert consultas["n"] == 1
    auth._revocar_token(token)


def test_desactivar_o_borrar_invalida_la_cache_al_momento(datos_auth):
    _crear_usuario("luis")
    token = auth._crear_sesion("luis")
    assert auth.usuario_desde_request(_Peticion(token)) is not None

    # Cambio en la base de datos seguido de la invalidación que hacen los
    # endpoints (cambiar_estado_usuario / eliminar_usuario cierran sesiones).
    with auth._db() as conn:
        conn.execute("UPDATE users SET disabled = 1 WHERE username = 'luis'")
    token2 = auth._crear_sesion("luis")
    auth._cerrar_sesiones_usuario("luis")
    assert auth.usuario_desde_request(_Peticion(token)) is None
    assert auth.usuario_desde_request(_Peticion(token2)) is None

    # Aunque quedara una sesión, el usuario desactivado ya no está en caché.
    token3 = auth._crear_sesion("luis")
    assert auth.usuario_desde_request(_Peticion(token3)) is None
    auth._revocar_token(token3)


def test_cambios_externos_se_ven_al_caducar_la_cache(datos_auth, monkeypatch):
    monkeypatch.setattr(auth, "USUARIO_CACHE_SEGUNDOS", 0.05)
    _crear_usuario("eva")
    token = auth._crear_sesion("eva")
    assert auth.usuario_desde_request(_Peticion(token)) is not None
    # Otro proceso (tipo-auth en otro contenedor) desactiva el usuario.
    conn = sqlite3.connect(str(auth._db_path()))
    conn.execute("UPDATE users SET disabled = 1 WHERE username = 'eva'")
    conn.commit()
    conn.close()
    time.sleep(0.1)
    assert auth.usuario_desde_request(_Peticion(token)) is None
    auth._revocar_token(token)


def test_cache_separada_por_base_de_datos(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_DISABLED", False)
    auth._invalidar_cache_usuarios()
    for nombre, rol in (("a", "admin"), ("b", "user")):
        carpeta = tmp_path / nombre
        monkeypatch.setattr(auth, "DATA_DIR", carpeta)
        monkeypatch.setattr(auth, "USERS_FILE", carpeta / "users.json")
        _crear_usuario("mismo", rol)
        token = auth._crear_sesion("mismo")
        assert auth.usuario_desde_request(_Peticion(token))["role"] == rol
        auth._revocar_token(token)
    auth._invalidar_cache_usuarios()
