"""
Protección contra Cross-Site Request Forgery (CSRF).

Capas:
    1. Origin / Referer check para peticiones mutadoras.
    2. Coincidencia exacta con el Host local de la aplicación.
    3. Token sincronizado en cabecera X-CSRF-Token.

Diseño monousuario/local: los tokens viven en memoria, tienen TTL y el
almacén está acotado para que /api/csrf no pueda crecer indefinidamente.
CSRF no es autenticación; no debe usarse como control de acceso en red.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import threading
import time
from urllib.parse import urlparse

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


# =============================================================================
# Configuración
# =============================================================================

HOSTS_PERMITIDOS: set[str] = {
    "localhost",
    "127.0.0.1",
    "[::1]",
    "::1",
}

ESQUEMAS_PERMITIDOS: set[str] = {"http"}
METODOS_MUTADORES = {"POST", "PUT", "PATCH", "DELETE"}

RUTAS_EXENTAS = {
    "/api/estado",
    "/api/csrf",
    # La configuración inicial y el login deben funcionar incluso en
    # navegadores/entornos que omiten Origin/Referer en localhost.
    # El resto de rutas autenticadas mantiene protección CSRF.
    "/api/auth/setup",
    "/api/auth/login",
    "/api/auth/logout",
}

TOKEN_TTL_SEGUNDOS = 8 * 60 * 60
MAX_TOKENS_VALIDOS = 16


def _host_local_valido(host: str | None) -> bool:
    if not host:
        return False
    try:
        p = urlparse(f"//{host}")
    except Exception:
        return False
    hostname = p.hostname
    return hostname in HOSTS_PERMITIDOS


def _origen_coincide_con_host(origen: str, request: Request) -> bool:
    """
    Exige que Origin/Referer sea exactamente el mismo origen local de la app.

    Ejemplo válido: Host localhost:8082 y Origin http://localhost:8082.
    Ejemplo rechazado: Host localhost:8082 y Origin http://localhost:9999.
    """
    try:
        origen_p = urlparse(origen)
    except Exception:
        return False

    if origen_p.scheme not in ESQUEMAS_PERMITIDOS:
        return False

    host_header = request.headers.get("host")
    if not _host_local_valido(host_header):
        return False

    host_p = urlparse(f"//{host_header}")
    if origen_p.hostname not in HOSTS_PERMITIDOS:
        return False

    if origen_p.hostname != host_p.hostname:
        return False

    # Si no hay puerto en el origen, se asume el puerto HTTP por defecto.
    origen_puerto = origen_p.port or (80 if origen_p.scheme == "http" else 443)
    host_puerto = host_p.port or (80 if origen_p.scheme == "http" else 443)
    return origen_puerto == host_puerto


# =============================================================================
# Almacén de tokens
# =============================================================================

_tokens_validos: dict[str, float] = {}
_tokens_lock = threading.Lock()


def _purgar_tokens(now: float | None = None) -> None:
    now = now or time.time()
    caducados = [
        token for token, emitido in _tokens_validos.items()
        if now - emitido > TOKEN_TTL_SEGUNDOS
    ]
    for token in caducados:
        _tokens_validos.pop(token, None)

    # Cap de memoria: conservar los más recientes.
    while len(_tokens_validos) > MAX_TOKENS_VALIDOS:
        mas_antiguo = min(_tokens_validos, key=_tokens_validos.get)
        _tokens_validos.pop(mas_antiguo, None)


def generar_token() -> str:
    """Emite un token CSRF nuevo y descarta tokens caducados/antiguos."""
    token = secrets.token_urlsafe(32)
    with _tokens_lock:
        _purgar_tokens()
        _tokens_validos[token] = time.time()
        _purgar_tokens()
    return token


def token_valido(candidato: str | None) -> bool:
    """Verifica si un token está vivo. Timing-safe frente a tokens válidos."""
    if not candidato:
        return False

    with _tokens_lock:
        _purgar_tokens()
        tokens = list(_tokens_validos.keys())

    encontrado = False
    for valido in tokens:
        if hmac.compare_digest(candidato, valido):
            encontrado = True
    return encontrado


# =============================================================================
# Comprobaciones
# =============================================================================

def _extraer_origen(request: Request) -> str | None:
    """Devuelve el origen de la petición.

    Prefiere Origin y usa Referer como fallback. Algunos navegadores pueden
    omitir ambas cabeceras en peticiones same-origin cuando la política de
    referencia es restrictiva; para ese caso se acepta Sec-Fetch-Site:
    same-origin, siempre que el Host sea local y el token CSRF sea válido.
    """
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")

    referer = request.headers.get("referer")
    if referer:
        try:
            p = urlparse(referer)
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}"
        except Exception:
            return None

    if request.headers.get("sec-fetch-site", "").lower() == "same-origin":
        host = request.headers.get("host")
        if _host_local_valido(host):
            return f"http://{host}"

    return None


def _peticion_exenta(request: Request) -> bool:
    if request.method not in METODOS_MUTADORES:
        return True
    # Se usa la ruta ASGI cruda (scope["path"]); request.url.path se reconstruye
    # desde la cabecera Host y es manipulable (BadHost / CVE-2026-48710), lo que
    # permitiría eludir la exención CSRF sobre una ruta distinta a la real.
    if request.scope.get("path", "") in RUTAS_EXENTAS:
        return True
    return False


def _respuesta_403(mensaje: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": mensaje},
        headers={"Cache-Control": "no-store"},
    )


# =============================================================================
# Middleware
# =============================================================================

def _peticion_cruzada_de_navegador(request: Request) -> str | None:
    """Para rutas exentas de token (setup, login, logout): devuelve un motivo
    si la petición llega desde otra web abierta en el navegador.

    Esas rutas no pueden exigir token CSRF (no hay sesión todavía), pero un
    navegador siempre declara de dónde viene una petición entre sitios: con
    Sec-Fetch-Site y con Origin. Si alguna de las dos delata un origen ajeno,
    se rechaza. Los clientes que no son navegador (curl, scripts locales) no
    envían esas cabeceras y siguen funcionando.
    """
    sec_fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    if sec_fetch_site in {"cross-site", "same-site"}:
        return f"Sec-Fetch-Site={sec_fetch_site}"
    origen = request.headers.get("origin") or None
    if origen is None:
        referer = request.headers.get("referer")
        if referer:
            try:
                p = urlparse(referer)
                if p.scheme and p.netloc:
                    origen = f"{p.scheme}://{p.netloc}"
            except Exception:
                return "Referer no válido"
    if origen is not None and not _origen_coincide_con_host(origen.rstrip("/"), request):
        return f"origen {origen}"
    return None


class ProteccionCSRF(BaseHTTPMiddleware):
    """Rechaza peticiones mutadoras sin Origin/Referer local y token válido."""

    async def dispatch(self, request: Request, call_next):
        if request.method in METODOS_MUTADORES and request.scope.get("path", "") in RUTAS_EXENTAS:
            # Exentas de token, pero no de la comprobación de origen: impide
            # que una web maliciosa abierta en el navegador reclame la cuenta
            # de administrador inicial o fuerce inicios de sesión.
            motivo = _peticion_cruzada_de_navegador(request)
            if motivo:
                logger.warning(
                    "CSRF: petición %s %s rechazada en ruta exenta (%s)",
                    request.method, request.scope.get("path", ""), motivo,
                )
                return _respuesta_403(
                    "Petición rechazada: esta operación solo puede hacerse desde la propia "
                    "aplicación en localhost."
                )
            return await call_next(request)

        if _peticion_exenta(request):
            return await call_next(request)

        origen = _extraer_origen(request)
        if origen is None:
            logger.warning(
                "CSRF: petición %s %s rechazada (sin Origin ni Referer)",
                request.method, request.scope.get("path", ""),
            )
            return _respuesta_403(
                "Petición rechazada: falta cabecera Origin. "
                "Si está usando la aplicación desde el navegador en localhost, recargue la página."
            )
        if not _origen_coincide_con_host(origen, request):
            logger.warning(
                "CSRF: petición %s %s rechazada (origen no coincide: %s; host: %s)",
                request.method, request.scope.get("path", ""), origen, request.headers.get("host"),
            )
            return _respuesta_403(
                f"Petición rechazada: origen no permitido ({origen}). "
                "Esta aplicación solo acepta peticiones desde su propio origen local."
            )

        token = request.headers.get("x-csrf-token")
        if not token_valido(token):
            logger.warning(
                "CSRF: petición %s %s rechazada (token inválido o ausente)",
                request.method, request.scope.get("path", ""),
            )
            return _respuesta_403(
                "Petición rechazada: token CSRF ausente, caducado o inválido. "
                "Recargue la página para obtener un token nuevo."
            )

        return await call_next(request)
