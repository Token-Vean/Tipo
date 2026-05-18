"""
Endpoints HTTP del procesamiento por lotes.

Se monta como router independiente desde main.py. Hereda toda la protección
existente: ProteccionAccesoLocal, ProteccionAutenticacion, ProteccionCSRF y
LimiteCuerpoPeticion. NO duplica la lógica de procesamiento: delega en
app/lotes.py.
"""

from __future__ import annotations

import json
import logging
import os
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from . import lotes
from . import exportadores_lote
from .version import APP_VERSION

logger = logging.getLogger(__name__)

router = APIRouter()


# Mismas normas que api.py para mantener coherencia.
NORMAS_VALIDAS = {"marc21-monografias"}
MODOS_VALIDOS = {"esencial", "completo", "personalizado"}
IDIOMAS_VALIDOS = {"es", "en"}
AGRUPACIONES_VALIDAS = {"un_libro_por_fichero", "un_libro_por_zip"}
FORMATOS_EXPORT = {"json", "csv", "isbd", "marcxml", "marc-txt", "zip"}


def _usuario(request: Request) -> str:
    user = getattr(request.state, "usuario", None)
    if not user or not user.get("username"):
        raise HTTPException(401, "Sesión no iniciada.")
    return str(user["username"])


def _parsear_etiquetas(etiquetas: str | None) -> list[str] | None:
    if not etiquetas:
        return None
    try:
        data = json.loads(etiquetas)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        # Aceptar formato coma-separado como fallback.
        return [x.strip() for x in etiquetas.split(",") if x.strip()]
    return None


@router.post("/lote")
async def crear_lote_endpoint(
    request: Request,
    ficheros: list[UploadFile] = File(...),
    etiquetas: str | None = Form(None),
    norma: str = Form("marc21-monografias"),
    modo: str = Form("esencial"),
    campos: str | None = Form(None),
    idioma_salida: str = Form("es"),
    modelo: str = Form(""),
    incognito: str = Form("0"),
    agrupacion: str = Form("un_libro_por_fichero"),
):
    username = _usuario(request)

    if norma not in NORMAS_VALIDAS:
        raise HTTPException(400, f"Norma no soportada: {norma}")
    if modo not in MODOS_VALIDOS:
        raise HTTPException(400, f"Modo no soportado: {modo}")
    if idioma_salida not in IDIOMAS_VALIDOS:
        raise HTTPException(400, f"Idioma no soportado: {idioma_salida}")
    if agrupacion not in AGRUPACIONES_VALIDAS:
        raise HTTPException(400, f"Agrupación no soportada: {agrupacion}")

    # Validar modelo igual que api.py
    from .api import _sanear_modelo, _validar_modelo_instalado
    modelo_seleccionado = _sanear_modelo(modelo if modelo else None)
    await _validar_modelo_instalado(modelo_seleccionado)

    incognito_b = incognito.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}

    try:
        lote_id = await lotes.crear_lote(
            ficheros=ficheros,
            agrupacion=agrupacion,
            norma=norma,
            modo=modo,
            campos=campos,
            idioma_salida=idioma_salida,
            modelo=modelo_seleccionado,
            incognito=incognito_b,
            etiquetas=_parsear_etiquetas(etiquetas),
            username=username,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    # Garantizar que el worker está vivo (idempotente).
    await lotes.iniciar_worker_si_inactivo()

    return {
        "lote_id": lote_id,
        "estado_inicial": "pendiente",
        "version_tipo": APP_VERSION,
    }


@router.get("/lote")
async def listar_lotes_endpoint(request: Request, limite: int = 50):
    username = _usuario(request)
    items = lotes.listar_lotes(username, limite=limite)
    return {"lotes": [it.to_dict() for it in items]}


@router.get("/lote/{lote_id}")
async def obtener_lote_endpoint(request: Request, lote_id: str):
    username = _usuario(request)
    lote = lotes.obtener_lote(lote_id, username=username)
    if not lote:
        raise HTTPException(404, "Lote no encontrado.")
    items = lotes.listar_items(lote_id)
    return {
        "lote": lote.to_dict(),
        "items": [it.to_dict() for it in items],
    }


@router.get("/lote/{lote_id}/item/{item_id}")
async def obtener_resultado_item_endpoint(request: Request, lote_id: str, item_id: str):
    username = _usuario(request)
    lote = lotes.obtener_lote(lote_id, username=username)
    if not lote:
        raise HTTPException(404, "Lote no encontrado.")
    payload = lotes.leer_resultado_item(lote_id, item_id)
    if not payload:
        raise HTTPException(404, "Resultado no disponible (item no terminado o sin resultado).")
    return payload


@router.post("/lote/{lote_id}/cancelar")
async def cancelar_lote_endpoint(request: Request, lote_id: str):
    username = _usuario(request)
    if not lotes.cancelar_lote(lote_id, username):
        raise HTTPException(404, "Lote no encontrado o no cancelable.")
    return {"ok": True}


@router.delete("/lote/{lote_id}")
async def borrar_lote_endpoint(request: Request, lote_id: str):
    username = _usuario(request)
    if not lotes.borrar_lote(lote_id, username):
        raise HTTPException(
            409,
            "El lote no puede borrarse en este momento (cancélalo primero si está en proceso).",
        )
    return {"ok": True}


@router.get("/lote/{lote_id}/exportar/{formato}")
async def exportar_lote_endpoint(request: Request, lote_id: str, formato: str):
    username = _usuario(request)
    if formato not in FORMATOS_EXPORT:
        raise HTTPException(400, f"Formato no soportado: {formato}")
    lote = lotes.obtener_lote(lote_id, username=username)
    if not lote:
        raise HTTPException(404, "Lote no encontrado.")

    items = lotes.listar_items(lote_id)
    payloads: list[dict[str, Any]] = []
    for it in items:
        if it.estado != "listo":
            continue
        p = lotes.leer_resultado_item(lote_id, it.id)
        if p:
            payloads.append(p)
    if not payloads:
        raise HTTPException(404, "El lote no tiene resultados disponibles para exportar.")

    contenido, mime, nombre = exportadores_lote.exportar_lote(formato, payloads, lote_id=lote_id)
    return Response(
        content=contenido,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
