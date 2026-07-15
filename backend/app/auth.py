
"""
Autenticación local de Tipo.

Diseño de preproducción beta:
- Usuarios locales persistidos en SQLite (/app/data/tipo_auth.sqlite3).
- Migración automática desde el antiguo users.json si existe.
- Hash PBKDF2-HMAC-SHA256 con sal aleatoria.
- Sesiones en memoria mediante cookie HttpOnly SameSite=Strict.
- Límite de intentos de login y bloqueo temporal por usuario/IP.
- Registro mínimo de eventos de seguridad en SQLite.

No es un IAM corporativo. Es una capa adicional para instalaciones locales o
personales y para evitar accesos accidentales desde el navegador o desde otras
sesiones del mismo equipo.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

VALORES_TRUE = {"1", "true", "yes", "si", "sí", "on"}
DATA_DIR = Path(os.getenv("TIPO_DATA_DIR", "/app/data"))
# Se conserva USERS_FILE por compatibilidad/migración desde beta.2.
USERS_FILE = DATA_DIR / "users.json"
SQLITE_FILE_NAME = os.getenv("TIPO_AUTH_DB_NAME", "tipo_auth.sqlite3")
AUTH_DISABLED = os.getenv("TIPO_AUTH_DISABLED", "false").strip().lower() in VALORES_TRUE
COOKIE_NAME = os.getenv("TIPO_SESSION_COOKIE", "tipo_session")
COOKIE_SECURE = os.getenv("TIPO_COOKIE_SECURE", "false").strip().lower() in VALORES_TRUE
SESSION_TTL_SECONDS = max(900, int(os.getenv("TIPO_SESSION_TTL_SECONDS", str(12 * 60 * 60))))
PBKDF2_ITERATIONS = max(200_000, int(os.getenv("TIPO_PBKDF2_ITERATIONS", "310000")))
USERNAME_RE = re.compile(r"^[a-zA-Z0-9._@-]{3,64}$")
PASSWORD_MIN_LENGTH = int(os.getenv("TIPO_PASSWORD_MIN_LENGTH", "10"))
LOGIN_MAX_ATTEMPTS = max(3, int(os.getenv("TIPO_LOGIN_MAX_ATTEMPTS", "6")))
LOGIN_LOCK_SECONDS = max(60, int(os.getenv("TIPO_LOGIN_LOCK_SECONDS", "300")))

PUBLIC_API_PATHS = {
    "/api/estado",
    "/api/csrf",
    "/api/auth/status",
    "/api/auth/setup",
    "/api/auth/login",
    "/api/auth/logout",
}

_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.Lock()
_users_lock = threading.RLock()
_login_failures: dict[str, dict[str, Any]] = {}

router = APIRouter(prefix="/auth", tags=["auth"])


class SetupPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=256)


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UsuarioNuevoPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=256)
    role: str = "user"


class CambiarPasswordPayload(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=256)


class ResetPasswordPayload(BaseModel):
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=256)


class EstadoUsuarioPayload(BaseModel):
    disabled: bool


def _db_path() -> Path:
    return DATA_DIR / SQLITE_FILE_NAME


def _legacy_users_file() -> Path:
    return USERS_FILE


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        DATA_DIR.chmod(0o700)
    except OSError:
        # En Docker Desktop/volúmenes Windows puede no ser aplicable.
        pass


def _connect() -> sqlite3.Connection:
    _ensure_data_dir()
    conn = sqlite3.connect(str(_db_path()), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','user')),
            disabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            last_login_at TEXT,
            password_changed_at TEXT,
            recovered_at TEXT,
            password_reset_by TEXT,
            failed_login_count INTEGER NOT NULL DEFAULT 0,
            last_failed_login_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT,
            target TEXT,
            client TEXT,
            detail TEXT
        )
        """
    )
    try:
        _db_path().chmod(0o600)
    except OSError:
        pass


def _row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "password_hash": row["password_hash"],
        "role": row["role"],
        "disabled": bool(row["disabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
        "password_changed_at": row["password_changed_at"],
        "recovered_at": row["recovered_at"],
        "password_reset_by": row["password_reset_by"],
        "failed_login_count": int(row["failed_login_count"] or 0),
        "last_failed_login_at": row["last_failed_login_at"],
    }


def _migrate_legacy_json_if_needed(conn: sqlite3.Connection) -> None:
    count = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    legacy = _legacy_users_file()
    if count or not legacy.exists():
        return
    try:
        with legacy.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        users = data.get("users", {}) if isinstance(data, dict) else {}
        if not isinstance(users, dict):
            return
        now = _now_iso()
        for username, user in users.items():
            if not isinstance(user, dict):
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO users
                (username, password_hash, role, disabled, created_at, updated_at, last_login_at,
                 password_changed_at, recovered_at, password_reset_by, failed_login_count, last_failed_login_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    str(user.get("password_hash", "")),
                    user.get("role", "user") if user.get("role") in {"admin", "user"} else "user",
                    1 if user.get("disabled") else 0,
                    user.get("created_at") or now,
                    user.get("updated_at"),
                    user.get("last_login_at"),
                    user.get("password_changed_at"),
                    user.get("recovered_at"),
                    user.get("password_reset_by"),
                    int(user.get("failed_login_count", 0) or 0),
                    user.get("last_failed_login_at"),
                ),
            )
        _record_event(conn, "legacy_users_json_migrated", actor="system", detail=str(legacy))
        try:
            legacy.rename(legacy.with_suffix(".json.migrated"))
        except OSError:
            pass
    except (OSError, json.JSONDecodeError, sqlite3.Error) as exc:
        logger.warning("No se pudo migrar users.json a SQLite: %s", exc)


def _db() -> sqlite3.Connection:
    conn = _connect()
    _ensure_schema(conn)
    _migrate_legacy_json_if_needed(conn)
    return conn


def _empty_store() -> dict[str, Any]:
    return {"version": 2, "backend": "sqlite", "users": {}}


def _load_store() -> dict[str, Any]:
    """Compatibilidad interna/CLI: devuelve usuarios en forma dict."""
    try:
        with _db() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
            return {"version": 2, "backend": "sqlite", "users": {r["username"]: _row_to_user(r) for r in rows}}
    except sqlite3.Error as exc:
        raise RuntimeError("El almacén local SQLite de usuarios está dañado o no es legible.") from exc


def _save_store(data: dict[str, Any]) -> None:
    """Compatibilidad interna/CLI: reemplaza la tabla de usuarios desde dict."""
    try:
        with _users_lock:
            with _db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM users")
                now = _now_iso()
                for username, user in data.get("users", {}).items():
                    if not isinstance(user, dict):
                        continue
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO users
                        (username, password_hash, role, disabled, created_at, updated_at, last_login_at,
                         password_changed_at, recovered_at, password_reset_by, failed_login_count, last_failed_login_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            username,
                            str(user.get("password_hash", "")),
                            user.get("role", "user") if user.get("role") in {"admin", "user"} else "user",
                            1 if user.get("disabled") else 0,
                            user.get("created_at") or now,
                            user.get("updated_at"),
                            user.get("last_login_at"),
                            user.get("password_changed_at"),
                            user.get("recovered_at"),
                            user.get("password_reset_by"),
                            int(user.get("failed_login_count", 0) or 0),
                            user.get("last_failed_login_at"),
                        ),
                    )
                conn.execute("COMMIT")
    except PermissionError as exc:
        logger.exception("No se puede escribir el almacén local SQLite en %s", _db_path())
        raise RuntimeError(
            "No se puede crear el usuario: el volumen local de datos no es escribible. "
            "Ejecute la opción 'Reparar permisos' desde el instalador/panel de Tipo "
            "o reinstale esta versión."
        ) from exc
    except sqlite3.Error as exc:
        logger.exception("Error escribiendo el almacén local SQLite en %s", _db_path())
        raise RuntimeError(
            "No se puede escribir el almacén local de usuarios. Revise permisos, espacio en disco "
            "o el estado de Docker."
        ) from exc


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _client_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "local"
    return f"{host}:{username.strip().lower()}"


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iter_s, salt_b64, digest_b64 = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_s)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def _validar_usuario(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(400, "El nombre de usuario debe tener 3-64 caracteres y usar solo letras, números, punto, guion, guion bajo o @.")
    return username


def _validar_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(400, f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.")
    if password.strip() != password:
        raise HTTPException(400, "La contraseña no debe empezar ni terminar con espacios.")
    clases = 0
    clases += any(c.islower() for c in password)
    clases += any(c.isupper() for c in password)
    clases += any(c.isdigit() for c in password)
    clases += any(not c.isalnum() for c in password)
    if clases < 3:
        raise HTTPException(400, "La contraseña debe combinar al menos tres tipos: minúsculas, mayúsculas, números o símbolos.")


def _record_event(
    conn: sqlite3.Connection,
    event_type: str,
    *,
    actor: str | None = None,
    target: str | None = None,
    client: str | None = None,
    detail: str | None = None,
) -> None:
    try:
        conn.execute(
            "INSERT INTO security_events(created_at, event_type, actor, target, client, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (_now_iso(), event_type, actor, target, client, detail),
        )
    except sqlite3.Error:
        logger.debug("No se pudo registrar evento de seguridad", exc_info=True)


def _check_login_lock(request: Request, username: str) -> None:
    key = _client_key(request, username)
    item = _login_failures.get(key)
    if not item:
        return
    locked_until = float(item.get("locked_until", 0) or 0)
    if locked_until > time.time():
        wait = int(max(1, locked_until - time.time()))
        raise HTTPException(429, f"Demasiados intentos fallidos. Espere {wait} segundos antes de volver a intentarlo.")


def _register_login_failure(request: Request, username: str) -> None:
    key = _client_key(request, username)
    item = _login_failures.setdefault(key, {"count": 0, "locked_until": 0})
    item["count"] = int(item.get("count", 0)) + 1
    if item["count"] >= LOGIN_MAX_ATTEMPTS:
        item["locked_until"] = time.time() + LOGIN_LOCK_SECONDS
    host = request.client.host if request.client else "local"
    try:
        with _db() as conn:
            conn.execute(
                "UPDATE users SET failed_login_count = failed_login_count + 1, last_failed_login_at = ? WHERE username = ?",
                (_now_iso(), username),
            )
            _record_event(conn, "login_failed", target=username, client=host)
    except Exception:
        logger.debug("No se pudo registrar intento fallido", exc_info=True)


def _clear_login_failures(request: Request, username: str) -> None:
    _login_failures.pop(_client_key(request, username), None)


def hay_usuarios() -> bool:
    if AUTH_DISABLED:
        return True
    with _users_lock:
        try:
            with _db() as conn:
                return bool(conn.execute("SELECT 1 FROM users LIMIT 1").fetchone())
        except RuntimeError:
            return False


def setup_requerido() -> bool:
    return not AUTH_DISABLED and not hay_usuarios()


def _sanear_salida_usuario(username: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": username,
        "role": data.get("role", "user"),
        "created_at": data.get("created_at"),
        "last_login_at": data.get("last_login_at"),
        "password_changed_at": data.get("password_changed_at"),
        "failed_login_count": int(data.get("failed_login_count", 0) or 0),
        "last_failed_login_at": data.get("last_failed_login_at"),
        "disabled": bool(data.get("disabled", False)),
    }


def _crear_sesion(username: str) -> str:
    token = secrets.token_urlsafe(48)
    now = time.time()
    with _sessions_lock:
        _purgar_sesiones(now)
        _sessions[token] = {"username": username, "created": now, "expires": now + SESSION_TTL_SECONDS}
    return token


def _purgar_sesiones(now: float | None = None) -> None:
    now = now or time.time()
    for token, data in list(_sessions.items()):
        if float(data.get("expires", 0)) < now:
            _sessions.pop(token, None)


def _cerrar_sesiones_usuario(username: str, *, excepto_token: str | None = None) -> None:
    with _sessions_lock:
        for token, data in list(_sessions.items()):
            if token == excepto_token:
                continue
            if data.get("username") == username:
                _sessions.pop(token, None)


def _contar_admins_activos(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0])


def _get_user(conn: sqlite3.Connection, username: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    return _row_to_user(row)


def usuario_desde_request(request: Request) -> dict[str, Any] | None:
    if AUTH_DISABLED:
        return {"username": "local", "role": "admin"}
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    with _sessions_lock:
        _purgar_sesiones()
        session = _sessions.get(token)
        if not session:
            return None
        username = str(session.get("username"))
        # Renovación deslizante de sesión durante uso activo.
        session["expires"] = time.time() + SESSION_TTL_SECONDS
    with _users_lock:
        try:
            with _db() as conn:
                user = _get_user(conn, username)
        except RuntimeError:
            return None
        if not isinstance(user, dict) or user.get("disabled"):
            return None
        return {"username": username, "role": user.get("role", "user")}


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def _require_admin(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "usuario", None) or usuario_desde_request(request)
    if not user:
        raise HTTPException(401, "Sesión no iniciada.")
    if user.get("role") != "admin":
        raise HTTPException(403, "Se requiere usuario administrador.")
    return user


class ProteccionAutenticacion(BaseHTTPMiddleware):
    """Protege los endpoints /api/* salvo estado, CSRF y autenticación."""

    async def dispatch(self, request: Request, call_next):
        if AUTH_DISABLED:
            request.state.usuario = {"username": "local", "role": "admin"}
            return await call_next(request)

        # Seguridad: se lee la ruta ASGI cruda (scope["path"]), NO request.url.path.
        # request.url reconstruye la URL a partir de la cabecera Host, que un cliente
        # puede manipular (BadHost / CVE-2026-48710). Cualquier decisión de
        # autorización debe basarse en la ruta real que el router va a despachar.
        path = request.scope.get("path", "")
        if not path.startswith("/api/") or path in PUBLIC_API_PATHS:
            return await call_next(request)

        if setup_requerido():
            return JSONResponse(
                status_code=403,
                content={"detail": "Configuración inicial requerida.", "setup_required": True},
                headers={"Cache-Control": "no-store"},
            )

        user = usuario_desde_request(request)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Sesión no iniciada."},
                headers={"Cache-Control": "no-store"},
            )
        request.state.usuario = user
        return await call_next(request)


@router.get("/status")
async def auth_status(request: Request):
    user = usuario_desde_request(request)
    return {
        "auth_enabled": not AUTH_DISABLED,
        "setup_required": setup_requerido(),
        "authenticated": bool(user),
        "user": user,
        "security": {
            "backend": "sqlite",
            "session_ttl_seconds": SESSION_TTL_SECONDS,
            "login_max_attempts": LOGIN_MAX_ATTEMPTS,
            "login_lock_seconds": LOGIN_LOCK_SECONDS,
            "password_min_length": PASSWORD_MIN_LENGTH,
        },
    }


@router.post("/setup")
async def setup(payload: SetupPayload, response: Response, request: Request):
    if AUTH_DISABLED:
        raise HTTPException(400, "La autenticación está desactivada.")
    username = _validar_usuario(payload.username)
    _validar_password(payload.password)
    try:
        with _users_lock:
            with _db() as conn:
                if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                    raise HTTPException(409, "La configuración inicial ya se ha realizado.")
                now = _now_iso()
                conn.execute(
                    "INSERT INTO users(username, password_hash, role, disabled, created_at, password_changed_at) VALUES (?, ?, 'admin', 0, ?, ?)",
                    (username, _hash_password(payload.password), now, now),
                )
                _record_event(conn, "admin_created", actor=username, target=username, client=request.client.host if request.client else "local")
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(500, "No se puede crear el usuario: error en el almacén local SQLite.") from exc
    token = _crear_sesion(username)
    _set_session_cookie(response, token)
    logger.info("Usuario administrador local creado: %s", username)
    return {"ok": True, "user": {"username": username, "role": "admin"}}


@router.post("/login")
async def login(payload: LoginPayload, response: Response, request: Request):
    if AUTH_DISABLED:
        return {"ok": True, "user": {"username": "local", "role": "admin"}}
    username = payload.username.strip()
    _check_login_lock(request, username)
    with _users_lock:
        try:
            with _db() as conn:
                user = _get_user(conn, username)
                if not isinstance(user, dict) or user.get("disabled"):
                    _verify_password(payload.password, _hash_password("contraseña-ficticia-segura"))
                    _register_login_failure(request, username)
                    raise HTTPException(401, "Usuario o contraseña incorrectos.")
                if not _verify_password(payload.password, str(user.get("password_hash", ""))):
                    _register_login_failure(request, username)
                    raise HTTPException(401, "Usuario o contraseña incorrectos.")
                now = _now_iso()
                conn.execute("UPDATE users SET last_login_at = ?, failed_login_count = 0 WHERE username = ?", (now, username))
                _record_event(conn, "login_ok", actor=username, target=username, client=request.client.host if request.client else "local")
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(500, str(exc)) from exc
    _clear_login_failures(request, username)
    token = _crear_sesion(username)
    _set_session_cookie(response, token)
    return {"ok": True, "user": {"username": username, "role": user.get("role", "user")}}


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with _sessions_lock:
            _sessions.pop(token, None)
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/usuarios")
async def listar_usuarios(request: Request):
    _require_admin(request)
    with _users_lock:
        with _db() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
            return {"usuarios": [_sanear_salida_usuario(r["username"], _row_to_user(r)) for r in rows]}


@router.get("/me")
async def perfil_actual(request: Request):
    user_state = getattr(request.state, "usuario", None) or usuario_desde_request(request)
    if not user_state:
        raise HTTPException(401, "Sesión no iniciada.")
    with _users_lock:
        with _db() as conn:
            user = _get_user(conn, user_state["username"])
            if not user:
                raise HTTPException(404, "Usuario no encontrado.")
            return {"user": _sanear_salida_usuario(user_state["username"], user)}


@router.post("/usuarios")
async def crear_usuario(payload: UsuarioNuevoPayload, request: Request):
    admin = _require_admin(request)
    username = _validar_usuario(payload.username)
    _validar_password(payload.password)
    role = payload.role if payload.role in {"admin", "user"} else "user"
    with _users_lock:
        with _db() as conn:
            if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                raise HTTPException(409, "Ya existe un usuario con ese nombre.")
            now = _now_iso()
            conn.execute(
                "INSERT INTO users(username, password_hash, role, disabled, created_at, password_changed_at) VALUES (?, ?, ?, 0, ?, ?)",
                (username, _hash_password(payload.password), role, now, now),
            )
            _record_event(conn, "user_created", actor=admin.get("username"), target=username)
    return {"ok": True, "user": {"username": username, "role": role}}


@router.post("/password")
async def cambiar_password(payload: CambiarPasswordPayload, request: Request):
    user_state = getattr(request.state, "usuario", None) or usuario_desde_request(request)
    if not user_state:
        raise HTTPException(401, "Sesión no iniciada.")
    _validar_password(payload.new_password)
    username = user_state["username"]
    with _users_lock:
        with _db() as conn:
            user = _get_user(conn, username)
            if not isinstance(user, dict) or not _verify_password(payload.current_password, str(user.get("password_hash", ""))):
                raise HTTPException(401, "Contraseña actual incorrecta.")
            now = _now_iso()
            conn.execute("UPDATE users SET password_hash = ?, password_changed_at = ?, updated_at = ? WHERE username = ?", (_hash_password(payload.new_password), now, now, username))
            _record_event(conn, "password_changed", actor=username, target=username)
    _cerrar_sesiones_usuario(username, excepto_token=request.cookies.get(COOKIE_NAME))
    return {"ok": True}


@router.post("/usuarios/{username}/password")
async def resetear_password_usuario(username: str, payload: ResetPasswordPayload, request: Request):
    admin = _require_admin(request)
    username = _validar_usuario(username)
    _validar_password(payload.password)
    with _users_lock:
        with _db() as conn:
            if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                raise HTTPException(404, "Usuario no encontrado.")
            now = _now_iso()
            conn.execute(
                "UPDATE users SET password_hash = ?, password_changed_at = ?, updated_at = ?, password_reset_by = ? WHERE username = ?",
                (_hash_password(payload.password), now, now, admin.get("username"), username),
            )
            _record_event(conn, "password_reset", actor=admin.get("username"), target=username)
    _cerrar_sesiones_usuario(username)
    return {"ok": True}


@router.post("/usuarios/{username}/estado")
async def cambiar_estado_usuario(username: str, payload: EstadoUsuarioPayload, request: Request):
    admin = _require_admin(request)
    username = _validar_usuario(username)
    if username == admin.get("username") and payload.disabled:
        raise HTTPException(400, "No puede desactivar su propio usuario mientras está conectado.")
    with _users_lock:
        with _db() as conn:
            user = _get_user(conn, username)
            if not isinstance(user, dict):
                raise HTTPException(404, "Usuario no encontrado.")
            if payload.disabled and user.get("role") == "admin" and _contar_admins_activos(conn) <= 1:
                raise HTTPException(400, "No puede desactivar el último administrador activo.")
            now = _now_iso()
            conn.execute("UPDATE users SET disabled = ?, updated_at = ? WHERE username = ?", (1 if payload.disabled else 0, now, username))
            _record_event(conn, "user_disabled" if payload.disabled else "user_enabled", actor=admin.get("username"), target=username)
    if payload.disabled:
        _cerrar_sesiones_usuario(username)
    return {"ok": True, "user": {"username": username, "disabled": bool(payload.disabled)}}


@router.delete("/usuarios/{username}")
async def eliminar_usuario(username: str, request: Request):
    admin = _require_admin(request)
    username = _validar_usuario(username)
    if username == admin.get("username"):
        raise HTTPException(400, "No puede eliminar su propio usuario mientras está conectado.")
    with _users_lock:
        with _db() as conn:
            user = _get_user(conn, username)
            if not isinstance(user, dict):
                raise HTTPException(404, "Usuario no encontrado.")
            if user.get("role") == "admin" and not user.get("disabled") and _contar_admins_activos(conn) <= 1:
                raise HTTPException(400, "No puede eliminar el último administrador activo.")
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
            _record_event(conn, "user_deleted", actor=admin.get("username"), target=username)
    _cerrar_sesiones_usuario(username)
    return {"ok": True}
