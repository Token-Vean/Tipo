"""
API REST de Tipo.

Procesa un conjunto local de imágenes o documentos del libro y devuelve una
propuesta descriptiva revisable. No consulta servicios externos, no crea puntos
de acceso autorizados y no opera sobre sistemas bibliotecarios.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import signal
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from . import auditoria, bibliografico, extractor, llm, router as router_entrada
from .router import ErrorValidacion
from .local_access import exposicion_red_permitida
from .version import APP_VERSION

logger = logging.getLogger(__name__)

MODELO = os.getenv("MODELO_NOMBRE", "gemma4:e4b")
DIR_ESQUEMAS = Path(os.getenv("DIR_ESQUEMAS", "/app/schemas"))


_MODELO_SEGURO_RE = re.compile(r"^[A-Za-z0-9._:/@+-]{1,160}$")


def _sanear_modelo(nombre: str | None) -> str:
    candidato = (nombre or MODELO).strip()
    if not candidato or not _MODELO_SEGURO_RE.fullmatch(candidato):
        raise HTTPException(400, "Nombre de modelo no válido.")
    return candidato


def _modelo_equivalente(nombre: str, modelos: list[str]) -> bool:
    if nombre in modelos:
        return True
    if f"{nombre}:latest" in modelos:
        return True
    if ":" not in nombre and f"{nombre}:latest" in modelos:
        return True
    return False


async def _validar_modelo_instalado(nombre: str) -> None:
    try:
        modelos = await llm.modelos_disponibles()
    except Exception as exc:
        logger.exception("No se pudo consultar la lista de modelos de Ollama")
        raise HTTPException(503, "No se pudo consultar Ollama para validar los modelos disponibles.") from exc
    if not _modelo_equivalente(nombre, modelos):
        lista = ", ".join(modelos[:12]) if modelos else "ninguno"
        raise HTTPException(400, f"El modelo '{nombre}' no está descargado en Ollama. Modelos disponibles: {lista}")


MAX_DESCRIBIR_BODY_BYTES = int(os.getenv("MAX_DESCRIBIR_BODY_BYTES", str(router_entrada.TAMANO_MAXIMO_BYTES + 8 * 1024 * 1024)))
MAX_EXPORT_BODY_BYTES = int(os.getenv("MAX_EXPORT_BODY_BYTES", str(15 * 1024 * 1024)))
MAX_CAMPOS_EXPORTACION = int(os.getenv("MAX_CAMPOS_EXPORTACION", "250"))
MAX_LONGITUD_VALOR_EXPORTACION = int(os.getenv("MAX_LONGITUD_VALOR_EXPORTACION", "50000"))
MAX_LONGITUD_EVIDENCIA_EXPORTACION = int(os.getenv("MAX_LONGITUD_EVIDENCIA_EXPORTACION", "8000"))
MAX_ITEMS_LISTA_EXPORTACION = int(os.getenv("MAX_ITEMS_LISTA_EXPORTACION", "100"))
MAX_ARCHIVOS_CONJUNTO = int(os.getenv("MAX_ARCHIVOS_CONJUNTO", "12"))
MAX_PROCESAMIENTOS_SIMULTANEOS = max(1, int(os.getenv("MAX_PROCESAMIENTOS_SIMULTANEOS", "1")))
PERMITIR_APAGADO_UI = os.getenv("PERMITIR_APAGADO_UI", "true").strip().lower() in {"1", "true", "yes", "si", "sí", "on"}
INCLUIR_HASH_DOCUMENTO_AUDITORIA = os.getenv("INCLUIR_HASH_DOCUMENTO_AUDITORIA", "true").strip().lower() in {"1", "true", "yes", "si", "sí", "on"}

IDIOMAS_SALIDA_ADMITIDOS = {"es", "en"}
_SEM_PROCESAMIENTO = asyncio.Semaphore(MAX_PROCESAMIENTOS_SIMULTANEOS)

PERFILES_DISPONIBLES = {
    "marc21-monografias": {
        "archivo": "datos-bibliograficos-monografia.yaml",
        "nombre": "MARC21 descriptivo / ISBD",
        "titulo": "Monografías impresas modernas",
    }
}

CAMPOS_ESENCIALES = {
    "isbn", "deposito_legal", "titulo_principal", "subtitulo",
    "mencion_responsabilidad", "mencion_edicion", "lugar_publicacion", "editor",
    "fecha_publicacion", "extension", "dimensiones", "serie_transcrita",
    # Bloques ISBD ensamblados por área (revisión humana directa)
    "isbd_area_0", "isbd_area_1", "isbd_area_2", "isbd_area_4",
    "isbd_area_5", "isbd_area_6", "isbd_area_7", "isbd_area_8",
}


@dataclass
class ArchivoEntrada:
    etiqueta: str
    nombre: str
    sha256: str | None
    tipo_mime: str
    tamano_bytes: int
    paginas: int | None
    ruta_procesamiento: str


@dataclass
class ConjuntoProcesado:
    entrada: extractor.Entrada
    ruta: str
    nombre_original: str
    tipo_mime: str
    tamano_bytes: int
    paginas: int | None
    archivos: list[ArchivoEntrada]
    # Cobertura de zonas: qué se analizó realmente frente al documento
    # completo. Una entrada por archivo, en el mismo orden que `archivos`.
    cobertura: list[dict] = field(default_factory=list)


class LimiteCuerpoPeticion:
    """Rechaza cuerpos HTTP excesivos antes del parseo multipart/JSON."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        metodo = scope.get("method", "").upper()
        ruta = scope.get("path", "")
        limite = self._limite_para(metodo, ruta)
        if limite is None:
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        raw_len = headers.get(b"content-length")
        if raw_len is None:
            await self._enviar_json(send, 411, "Content-Length requerido para esta operación.")
            return
        try:
            longitud = int(raw_len.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            await self._enviar_json(send, 400, "Content-Length inválido.")
            return
        if longitud > limite:
            await self._enviar_json(send, 413, f"Cuerpo de petición demasiado grande. Máximo: {limite} bytes.")
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _limite_para(metodo: str, ruta: str) -> int | None:
        if metodo not in {"POST", "PUT", "PATCH"}:
            return None
        if ruta == "/api/describir":
            return MAX_DESCRIBIR_BODY_BYTES
        if ruta.startswith("/api/exportar/"):
            return MAX_EXPORT_BODY_BYTES
        return None

    @staticmethod
    async def _enviar_json(send: Send, status_code: int, detail: str) -> None:
        cuerpo = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": status_code, "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")]})
        await send({"type": "http.response.body", "body": cuerpo})


class CabecerasSeguridad(BaseHTTPMiddleware):
    """Aplica cabeceras de seguridad HTTP a todas las respuestas."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        respuesta = await call_next(request)
        respuesta.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; object-src 'none'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Referrer-Policy"] = "same-origin"
        respuesta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        if request.url.path.startswith("/api/"):
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta


def _log_peticion(evento: str, peticion_id: str, **kwargs: Any) -> None:
    if kwargs.pop("_incognito", False):
        # En modo incógnito solo dejamos constancia mínima del evento: sin
        # detalles, sin nombre de archivos, sin contadores.
        logger.info("[%s] %s (incognito)", peticion_id, evento)
        return
    extras = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info("[%s] %s %s", peticion_id, evento, extras)


_CARACTERES_RUTA_PELIGROSOS = re.compile(r'[\\/:*?"<>|]+')


def _sanear_texto_corto(valor: Any, max_len: int = 120, fallback: str = "sin_etiqueta") -> str:
    """Normaliza nombres de archivo/etiquetas antes de prompt, logs y auditoría.

    No es una validación de seguridad de contenidos; solo evita saltos de línea,
    caracteres de control, separadores de ruta y textos excesivamente largos en
    metadatos controlados por el usuario.
    """
    texto = "" if valor is None else str(valor)
    texto = "".join(ch if ch.isprintable() else " " for ch in texto)
    texto = _CARACTERES_RUTA_PELIGROSOS.sub(" ", texto)
    texto = " ".join(texto.split())
    if not texto:
        texto = fallback
    return texto[:max_len].strip() or fallback


router = APIRouter()


@router.get("/csrf")
async def emitir_token_csrf():
    from . import csrf
    return {"token": csrf.generar_token()}


@router.get("/normas")
async def listar_normas():
    return {"normas": [{"clave": clave, **datos} for clave, datos in PERFILES_DISPONIBLES.items()]}


@router.get("/modelos")
async def listar_modelos_ollama():
    """Devuelve modelos descargados en el Ollama configurado.

    La UI solo permite seleccionar modelos presentes en esta lista para evitar
    envíos accidentales a un endpoint distinto o errores de descarga implícita.
    Se devuelven metadatos enriquecidos y advertencias de capacidad.
    """
    try:
        modelos_meta = await llm.modelos_disponibles(detallado=True)
    except Exception as exc:
        logger.exception("No se pudo listar modelos de Ollama")
        raise HTTPException(503, "No se pudo consultar la lista de modelos de Ollama.") from exc
    nombres = [m.get("name") for m in modelos_meta if isinstance(m, dict) and m.get("name")]
    predeterminado = MODELO if _modelo_equivalente(MODELO, nombres) else (nombres[0] if nombres else MODELO)
    for m in modelos_meta:
        if isinstance(m, dict):
            m["recommended"] = m.get("name") == predeterminado
    return {
        "modelo_predeterminado": predeterminado,
        "modelos": nombres,
        "modelos_detalle": modelos_meta,
    }


@router.get("/diagnostico")
async def diagnostico_operativo(request: Request):
    """Diagnóstico local sin datos documentales. Requiere sesión iniciada."""
    return {
        "version": APP_VERSION,
        "local_only": not exposicion_red_permitida(),
        "shutdown_ui_enabled": PERMITIR_APAGADO_UI,
        "modelo_por_defecto": MODELO,
        "max_archivos": MAX_ARCHIVOS_CONJUNTO,
        "max_body_describir_bytes": MAX_DESCRIBIR_BODY_BYTES,
        "procesamientos_simultaneos": MAX_PROCESAMIENTOS_SIMULTANEOS,
        "cliente": request.client.host if request.client else "local",
        "alcance_beta": "monografia_moderna_impresa",
    }


async def _apagar_proceso_app() -> None:
    await asyncio.sleep(0.35)
    logger.info("Apagado solicitado desde la interfaz local")
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        logger.exception("No se pudo enviar SIGTERM; salida forzada")
        os._exit(0)


@router.post("/apagar")
async def apagar_desde_interfaz():
    if exposicion_red_permitida():
        raise HTTPException(
            403,
            "El apagado desde la interfaz no está disponible cuando ALLOW_NETWORK_EXPOSURE=true.",
        )
    if not PERMITIR_APAGADO_UI:
        raise HTTPException(403, "El apagado desde la interfaz está desactivado.")
    asyncio.create_task(_apagar_proceso_app())
    return {"ok": True, "mensaje": "Apagado iniciado. Tipo se detendrá en unos segundos."}


def _parsear_etiquetas(etiquetas: str | None, total: int) -> list[str]:
    if not etiquetas:
        return [f"imagen_{i + 1}" for i in range(total)]
    try:
        data = json.loads(etiquetas)
        if isinstance(data, list):
            out = [
                _sanear_texto_corto(x, 80, fallback=f"imagen_{i + 1}")
                for i, x in enumerate(data[:total])
            ]
        else:
            out = []
    except json.JSONDecodeError:
        out = [
            _sanear_texto_corto(x, 80, fallback=f"imagen_{i + 1}")
            for i, x in enumerate(etiquetas.split(","))
            if str(x).strip()
        ]
    while len(out) < total:
        out.append(f"imagen_{len(out) + 1}")
    return out[:total]


def _fusionar_documentos(docs: list[tuple[router_entrada.DocumentoProcesado, str, str | None]]) -> ConjuntoProcesado:
    textos: list[str] = []
    imagenes: list[bytes] = []
    etiquetas_imagenes: list[str] = []
    archivos: list[ArchivoEntrada] = []
    cobertura: list[dict] = []
    total_bytes = 0
    paginas_total = 0
    rutas = set()
    for doc, etiqueta, sha256 in docs:
        total_bytes += doc.tamano_bytes
        rutas.add(doc.ruta)
        if doc.paginas:
            paginas_total += doc.paginas
        archivos.append(ArchivoEntrada(etiqueta, doc.nombre_original, sha256, doc.tipo_mime, doc.tamano_bytes, doc.paginas, doc.ruta))
        # Cobertura de zonas de este archivo, etiquetada para la auditoría.
        cob = dict(doc.cobertura or {})
        cob["etiqueta"] = etiqueta
        cob["archivo"] = doc.nombre_original
        cobertura.append(cob)
        if doc.entrada.texto:
            textos.append(f"### Fuente: {etiqueta} — {doc.nombre_original}\n{doc.entrada.texto}")
        if doc.entrada.imagenes:
            # El router ya etiqueta cada imagen con su zona y página cuando
            # procede (zonas.etiquetas_para_indices). Se conserva esa etiqueta
            # y solo se completa con el nombre del archivo de origen.
            etiquetas_doc = doc.entrada.imagenes_etiquetas or []
            for idx, img in enumerate(doc.entrada.imagenes):
                imagenes.append(img)
                if idx < len(etiquetas_doc) and etiquetas_doc[idx]:
                    etiquetas_imagenes.append(f"{etiquetas_doc[idx]} — {doc.nombre_original}")
                else:
                    sufijo = f" página {idx + 1}" if len(doc.entrada.imagenes) > 1 else ""
                    etiquetas_imagenes.append(f"{etiqueta}{sufijo} — {doc.nombre_original}")
    if "hibrida" in rutas or ({"texto", "vision"} <= rutas):
        ruta = "hibrida"
    elif "vision" in rutas:
        ruta = "vision"
    else:
        ruta = "texto"
    entrada = extractor.Entrada(texto="\n\n".join(textos).strip() or None, imagenes=imagenes or None, imagenes_etiquetas=etiquetas_imagenes or None)
    nombres = ", ".join(a.nombre for a in archivos[:3]) + ("..." if len(archivos) > 3 else "")
    return ConjuntoProcesado(entrada, ruta, nombres or "conjunto_sin_nombre", "multipart/mixed" if len(archivos) > 1 else (archivos[0].tipo_mime if archivos else "unknown"), total_bytes, paginas_total or None, archivos, cobertura)


@router.post("/describir")
async def describir(
    ficheros: list[UploadFile] = File(...),
    etiquetas: str | None = Form(None),
    norma: str = Form("marc21-monografias"),
    modo: str = Form("esencial"),
    campos: str | None = Form(None),
    idioma_salida: str = Form("es"),
    modelo: str | None = Form(None),
    incognito: str = Form("0"),
):
    peticion_id = str(uuid.uuid4())[:8]
    incognito_modo = str(incognito or "0").strip().lower() in {"1", "true", "si", "sí", "yes", "on"}
    if norma not in PERFILES_DISPONIBLES:
        raise HTTPException(400, f"Perfil desconocido: {norma}")
    if modo not in ("esencial", "completo", "personalizado"):
        raise HTTPException(400, f"Modo desconocido: {modo}")
    idioma_salida = (idioma_salida or "es").strip().lower()
    if idioma_salida not in IDIOMAS_SALIDA_ADMITIDOS:
        raise HTTPException(400, f"Idioma de salida no admitido: {idioma_salida}")
    modelo_seleccionado = _sanear_modelo(modelo)
    await _validar_modelo_instalado(modelo_seleccionado)
    if not ficheros:
        raise HTTPException(400, "Debe subirse al menos una imagen o documento.")
    if len(ficheros) > MAX_ARCHIVOS_CONJUNTO:
        raise HTTPException(400, f"Demasiados archivos: máximo {MAX_ARCHIVOS_CONJUNTO}.")
    etiquetas_lista = _parsear_etiquetas(etiquetas, len(ficheros))
    async with _SEM_PROCESAMIENTO:
        _log_peticion("describir_inicio", peticion_id, norma=norma, modo=modo, modelo=modelo_seleccionado, archivos=len(ficheros), _incognito=incognito_modo)
        procesados: list[tuple[router_entrada.DocumentoProcesado, str, str | None]] = []
        for archivo, etiqueta in zip(ficheros, etiquetas_lista, strict=False):
            nombre_seguro = _sanear_texto_corto(archivo.filename or "sin_nombre", 180, "sin_nombre")
            contenido = await archivo.read()
            sha256 = hashlib.sha256(contenido).hexdigest() if INCLUIR_HASH_DOCUMENTO_AUDITORIA else None
            try:
                doc = router_entrada.procesar(contenido, nombre_seguro)
            except ErrorValidacion as e:
                _log_peticion("archivo_validacion_fallida", peticion_id, nombre=nombre_seguro, error=str(e))
                raise HTTPException(400, f"{nombre_seguro or 'archivo'}: {e}") from None
            except Exception as err:
                logger.exception("[%s] Error inesperado procesando archivo", peticion_id)
                raise HTTPException(500, "Error al procesar uno de los archivos.") from err
            finally:
                contenido = b""
            procesados.append((doc, etiqueta, sha256))
        conjunto = _fusionar_documentos(procesados)
        ruta_esquema = DIR_ESQUEMAS / PERFILES_DISPONIBLES[norma]["archivo"]
        try:
            esquema = extractor.cargar_esquema(ruta_esquema)
        except FileNotFoundError:
            raise HTTPException(500, f"Esquema no disponible: {norma}") from None
        except ValueError as e:
            raise HTTPException(500, f"Esquema inválido: {e}") from None
        filtro_claves = _construir_filtro(modo, campos, esquema)
        try:
            propuesta = await extractor.extraer(conjunto.entrada, esquema, modelo_seleccionado, filtro_claves, idioma_salida)
            bibliografico.aplicar_validaciones(propuesta)
            bibliografico.aplicar_bloques_isbd_a_propuesta(propuesta)
        except Exception as err:
            logger.exception("[%s] Error en extracción", peticion_id)
            raise HTTPException(500, "Error al generar la propuesta bibliográfica.") from err
        _log_peticion("describir_fin", peticion_id, campos=len(propuesta.campos), advertencias=len(propuesta.advertencias), _incognito=incognito_modo)
    ficha_tecnica = auditoria.generar_ficha_tecnica(peticion_id=peticion_id, documento=conjunto, esquema=esquema, modo=modo, idioma_salida=idioma_salida, modelo=modelo_seleccionado, filtro_claves=filtro_claves, propuesta=propuesta, deteccion=None, sha256_documento=None, incognito=incognito_modo)
    campos_dict = [c.__dict__ for c in propuesta.campos]
    isbd = bibliografico.generar_isbd_desde_campos(campos_dict)
    from . import exportadores as _exp
    marc21_lineas = _exp.generar_marc21_texto(campos_dict)
    marc21_texto = _exp.marc21_a_texto_plano(marc21_lineas)
    return {
        "peticion": peticion_id,
        "idioma_salida": idioma_salida,
        "modelo": modelo_seleccionado,
        "version_tipo": APP_VERSION,
        "documento": {"nombre": conjunto.nombre_original, "tipo_mime": conjunto.tipo_mime, "tamano_bytes": conjunto.tamano_bytes, "paginas": conjunto.paginas, "ruta_procesamiento": conjunto.ruta, "archivos": [a.__dict__ for a in conjunto.archivos], "cobertura_zonas": conjunto.cobertura},
        "auditoria": ficha_tecnica,
        "isbd": isbd,
        "marc21_lineas": marc21_lineas,
        "marc21_texto": marc21_texto,
        "propuesta": propuesta.to_dict(),
    }


def _construir_filtro(modo: str, campos_str: str | None, esquema: extractor.Esquema) -> set[str] | None:
    if modo == "completo":
        return None
    if modo == "esencial":
        return {e.clave for e in esquema.elementos if e.clave in CAMPOS_ESENCIALES and e.extraible != "no"}
    if modo == "personalizado":
        if not campos_str:
            raise HTTPException(400, "Modo personalizado requiere el parámetro 'campos'.")
        claves = {c.strip() for c in campos_str.split(",") if c.strip()}
        claves_validas = {e.clave for e in esquema.elementos}
        desconocidas = claves - claves_validas
        if desconocidas:
            raise HTTPException(400, f"Campos desconocidos: {', '.join(sorted(desconocidas))}")
        return claves
    return None


@router.post("/exportar/{formato}")
async def exportar(formato: str, payload: dict):
    formatos_validos = {"json", "csv", "isbd", "marcxml", "marc-txt"}
    if formato not in formatos_validos:
        raise HTTPException(400, f"Formato no soportado: {formato}")
    payload = _validar_payload_exportacion(payload)
    try:
        from . import exportadores
        contenido, mime, nombre = exportadores.exportar(formato=formato, propuesta=payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    except Exception as err:
        logger.exception("Error al generar exportación %s", formato)
        raise HTTPException(500, f"Error al generar el fichero {formato.upper()}.") from err
    return Response(content=contenido, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def _validar_payload_exportacion(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(400, "Payload inválido: se esperaba un objeto JSON.")
    propuesta = payload.get("propuesta")
    if not isinstance(propuesta, dict):
        raise HTTPException(400, "Payload inválido: falta el objeto 'propuesta'.")
    campos = propuesta.get("campos")
    if not isinstance(campos, list):
        raise HTTPException(400, "Payload inválido: 'propuesta.campos' debe ser una lista.")
    if len(campos) > MAX_CAMPOS_EXPORTACION:
        raise HTTPException(400, f"Demasiados campos para exportar: {len(campos)}; máximo {MAX_CAMPOS_EXPORTACION}.")
    try:
        tamano_logico = len(json.dumps(payload, ensure_ascii=False))
    except (TypeError, ValueError):
        raise HTTPException(400, "Payload inválido: contiene valores no serializables.") from None
    if tamano_logico > MAX_EXPORT_BODY_BYTES:
        raise HTTPException(413, "Payload de exportación demasiado grande.")
    for idx, campo in enumerate(campos):
        if not isinstance(campo, dict):
            raise HTTPException(400, f"Campo #{idx + 1} inválido: debe ser un objeto.")
        _validar_cadena_corta(campo.get("id"), "id", idx, 128)
        _validar_cadena_corta(campo.get("clave"), "clave", idx, 128)
        _validar_cadena_corta(campo.get("nombre"), "nombre", idx, 512)
        _validar_cadena_corta(campo.get("confianza"), "confianza", idx, 32, permitir_none=True)
        _validar_valor_exportacion(campo.get("valor"), idx)
        _validar_cadena_corta(campo.get("evidencia"), "evidencia", idx, MAX_LONGITUD_EVIDENCIA_EXPORTACION, permitir_none=True)
    return payload


def _validar_cadena_corta(valor: Any, nombre: str, idx: int, max_len: int, *, permitir_none: bool = False) -> None:
    if valor is None and permitir_none:
        return
    if valor is None:
        return
    if not isinstance(valor, str):
        raise HTTPException(400, f"Campo #{idx + 1}: '{nombre}' debe ser texto.")
    if len(valor) > max_len:
        raise HTTPException(400, f"Campo #{idx + 1}: '{nombre}' supera {max_len} caracteres.")
    _validar_sin_controles_peligrosos(valor, nombre, idx)


def _validar_valor_exportacion(valor: Any, idx: int) -> None:
    if valor in (None, ""):
        return
    if isinstance(valor, str):
        if len(valor) > MAX_LONGITUD_VALOR_EXPORTACION:
            raise HTTPException(400, f"Campo #{idx + 1}: valor demasiado largo.")
        _validar_sin_controles_peligrosos(valor, "valor", idx)
        return
    if isinstance(valor, list):
        if len(valor) > MAX_ITEMS_LISTA_EXPORTACION:
            raise HTTPException(400, f"Campo #{idx + 1}: lista demasiado larga.")
        for item in valor:
            if not isinstance(item, str):
                raise HTTPException(400, f"Campo #{idx + 1}: los valores de lista deben ser texto.")
            if len(item) > MAX_LONGITUD_VALOR_EXPORTACION:
                raise HTTPException(400, f"Campo #{idx + 1}: item de lista demasiado largo.")
            _validar_sin_controles_peligrosos(item, "valor", idx)
        return
    raise HTTPException(400, f"Campo #{idx + 1}: tipo de valor no admitido.")


def _validar_sin_controles_peligrosos(valor: str, nombre: str, idx: int) -> None:
    for ch in valor:
        o = ord(ch)
        if (o < 32 and ch not in "\n\r\t") or o == 127:
            raise HTTPException(400, f"Campo #{idx + 1}: '{nombre}' contiene caracteres de control no admitidos.")
