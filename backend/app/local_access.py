"""
Protección de exposición local.

Tipo está diseñado para uso local. Esta capa rechaza peticiones cuyo
encabezado Host no apunte a loopback, salvo que se active de forma explícita
ALLOW_NETWORK_EXPOSURE=true.

Qué protege y qué NO protege:

- SÍ protege frente a DNS rebinding: una web maliciosa que hace resolver su
  propio dominio a 127.0.0.1 envía su dominio en Host y queda rechazada.
- SÍ evita que el navegador use la aplicación por una IP de red local
  (http://192.168.x.x:8082) si el puerto llegara a publicarse por error.
- NO es un control de acceso de red. La cabecera Host la decide el cliente:
  cualquier programa que alcance el puerto puede enviar "Host: localhost".

El control de red real es la publicación del puerto solo en loopback
("127.0.0.1:${PUERTO}:8081" en docker-compose.yml). No cambie esa línea a
"0.0.0.0" ni use `-p 8082:8081` confiando en esta capa: si el puerto queda
expuesto, solo la autenticación separa la aplicación de la red.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1", "[::1]"}
VALORES_TRUE = {"1", "true", "yes", "si", "sí", "on"}


def _env_true(nombre: str, defecto: str = "false") -> bool:
    return os.getenv(nombre, defecto).strip().lower() in VALORES_TRUE


def exposicion_red_permitida() -> bool:
    return _env_true("ALLOW_NETWORK_EXPOSURE")


def _host_header_local(host_header: str | None) -> bool:
    if not host_header:
        return False
    try:
        parsed = urlparse(f"//{host_header}")
    except Exception:
        return False
    return parsed.hostname in HOSTS_LOCALES


class ProteccionAccesoLocal(BaseHTTPMiddleware):
    """Bloquea peticiones cuyo Host no sea local salvo opt-in explícito."""

    async def dispatch(self, request: Request, call_next):
        if exposicion_red_permitida():
            return await call_next(request)

        host_header = request.headers.get("host")
        if not _host_header_local(host_header):
            logger.warning(
                "Solicitud rechazada por Host no local: host=%r path=%s",
                host_header,
                request.scope.get("path", ""),
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "Tipo está configurado para uso local. "
                        "Acceda mediante http://localhost o http://127.0.0.1, "
                        "o active ALLOW_NETWORK_EXPOSURE=true bajo su responsabilidad."
                    )
                },
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        return await call_next(request)
