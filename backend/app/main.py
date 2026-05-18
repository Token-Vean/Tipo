"""
Punto de entrada de Tipo.

La aplicación mantiene el patrón local-first: backend FastAPI, frontend
estático, arranque de Ollama en segundo plano y bloqueo por defecto de
exposición fuera de localhost.

A partir de la entrega de procesamiento por lotes, el `lifespan` también
recupera lotes interrumpidos (huérfanos por reinicio brusco) y arranca un
único worker asyncio que consume la cola en serie.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import api, auth, bootstrap, lotes, lotes_api
from .api import CabecerasSeguridad, LimiteCuerpoPeticion
from .csrf import ProteccionCSRF
from .auth import ProteccionAutenticacion
from .local_access import ProteccionAccesoLocal
from .version import APP_NAME, APP_VERSION

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tarea = asyncio.create_task(bootstrap.preparar())
    # Recuperación de lotes interrumpidos y arranque del worker único.
    # Se ejecuta en un thread aparte por seguridad si SQLite estuviera ocupado.
    try:
        await asyncio.to_thread(lotes.recuperar_arranque)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Fallo en la recuperación de lotes; el worker arrancará igualmente"
        )
    await lotes.iniciar_worker_si_inactivo()
    try:
        yield
    finally:
        if not tarea.done():
            tarea.cancel()
        # Cierre ordenado del worker de lotes.
        try:
            await lotes.detener_worker()
        except Exception:  # noqa: BLE001
            logger.exception("Fallo al detener el worker de lotes en el cierre")


app = FastAPI(
    title=APP_NAME,
    description="Asistente local para extracción de datos bibliográficos y propuesta de campos descriptivos.",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(CabecerasSeguridad)
app.add_middleware(ProteccionCSRF)
app.add_middleware(LimiteCuerpoPeticion)
app.add_middleware(ProteccionAutenticacion)
app.add_middleware(ProteccionAccesoLocal)
app.include_router(auth.router, prefix="/api")
app.include_router(api.router, prefix="/api")
app.include_router(lotes_api.router, prefix="/api")


@app.get("/api/estado")
async def estado():
    return bootstrap.estado


DIR_STATIC = Path("/app/static")
if DIR_STATIC.exists():
    app.mount("/", StaticFiles(directory=str(DIR_STATIC), html=True), name="ui")
else:
    logger.warning("No se ha encontrado %s; sirviendo diagnóstico mínimo.", DIR_STATIC)
    from fastapi.responses import HTMLResponse

    @app.get("/")
    async def diagnostico():
        return HTMLResponse("""<!doctype html><meta charset='utf-8'><title>Tipo</title><body><h1>Tipo</h1><p>Backend operativo.</p></body>""")
