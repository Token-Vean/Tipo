"""
Procesamiento por lotes de Tipo.

Reutiliza el mismo pipeline que /api/describir (validación, sandbox, segmentación
por zonas, extracción guiada por esquema, validaciones bibliográficas, bloques
ISBD, MARC21) y lo aplica de forma desatendida a múltiples libros.

Diseño:

- Un único worker asíncrono (asyncio.Task creada en lifespan) consume una cola
  FIFO. NO se paraleliza la inferencia: Ollama serializa en CPU y el contenedor
  app ya impone _SEM_PROCESAMIENTO=1 por defecto.
- Persistencia en el mismo SQLite local que ya usa auth (/app/data/tipo_auth.sqlite3).
- Ficheros de entrada y resultados en /app/data/batches/<lote_id>/<item_id>/.
  El contenedor app es read_only:true salvo /app/data, que es el volumen tipo-data.
- Reentrancia: al arrancar, items 'en_proceso' huérfanos vuelven a 'pendiente'
  (con intentos += 1) o pasan a 'error' si superan TIPO_LOTE_REINTENTOS_MAX.
- Cancelación lógica: marca pendientes como 'cancelado'; el item en curso termina.
- Aislamiento por item: una excepción en un libro deja ese libro en 'error' y el
  lote continúa con el siguiente.
- Almacenamiento acotado: subida por bloques (nunca el fichero entero en
  memoria), cuota de disco por usuario, retención opcional por días, borrado de
  originales al terminar en modo incógnito y borrado de todos los lotes de un
  usuario cuando se elimina (o antes de reutilizar su nombre).

Este módulo NO procesa nada por sí mismo: delega en router.procesar() y
extractor.extraer(), que ya están endurecidos (sandbox, límites, evidencias).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import sqlite3
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from . import auditoria, bibliografico, extractor, router as router_entrada
from .router import ErrorValidacion
from .version import APP_VERSION

logger = logging.getLogger(__name__)


# =============================================================================
# Configuración
# =============================================================================

VALORES_TRUE = {"1", "true", "yes", "si", "sí", "on"}

DATA_DIR = Path(os.getenv("TIPO_DATA_DIR", "/app/data"))
LOTES_DIR = Path(os.getenv("TIPO_LOTE_DIR", str(DATA_DIR / "batches")))
SQLITE_FILE_NAME = os.getenv("TIPO_AUTH_DB_NAME", "tipo_auth.sqlite3")
DB_PATH = DATA_DIR / SQLITE_FILE_NAME

# Configuración del lote.
MAX_LIBROS_LOTE = max(1, int(os.getenv("TIPO_MAX_LIBROS_LOTE", "50")))
MAX_BYTES_LOTE = int(os.getenv("TIPO_MAX_BYTES_LOTE", str(2 * 1024 * 1024 * 1024)))  # 2 GB
REINTENTOS_MAX = max(0, int(os.getenv("TIPO_LOTE_REINTENTOS_MAX", "1")))

# ZIP de entrada (modo un_libro_por_zip). Más estrictos que MAX_TAMANO_FICHERO_BYTES.
ZIP_MAX_ENTRADAS = max(1, int(os.getenv("TIPO_LOTE_ZIP_MAX_ENTRADAS", "60")))
ZIP_MAX_DESCOMPRIMIDO = int(os.getenv("TIPO_LOTE_ZIP_MAX_DESCOMPRIMIDO", str(200 * 1024 * 1024)))
ZIP_MAX_RATIO = max(2, int(os.getenv("TIPO_LOTE_ZIP_MAX_RATIO", "100")))

# Almacenamiento persistente (auditoría 2026-10).
# - Cuota de disco por usuario sumando todos sus lotes (originales + resultados).
# - Retención opcional: los lotes finalizados o cancelados con más de N días se
#   borran solos (0 = desactivado, comportamiento anterior).
# - Originales: en modo incógnito se borran siempre en cuanto el libro termina;
#   en modo normal se conservan salvo TIPO_LOTE_CONSERVAR_ORIGINALES=false.
#   Las exportaciones usan solo result.json, así que borrar originales de un
#   libro ya terminado no afecta a nada que ofrezca la aplicación.
MAX_BYTES_USUARIO = int(os.getenv("TIPO_LOTE_MAX_BYTES_USUARIO", str(10 * 1024 * 1024 * 1024)))  # 10 GB
RETENCION_DIAS = max(0, int(os.getenv("TIPO_LOTE_RETENCION_DIAS", "0")))
CONSERVAR_ORIGINALES = os.getenv("TIPO_LOTE_CONSERVAR_ORIGINALES", "true").strip().lower() in VALORES_TRUE
_TROZO_SUBIDA = 1024 * 1024
_NOMBRE_ZIP_TEMPORAL = "_subida.zip.tmp"

ESTADOS_LOTE = {"pendiente", "en_proceso", "finalizado", "cancelado"}
ESTADOS_ITEM = {"pendiente", "en_proceso", "listo", "error", "cancelado"}

# Cola en memoria. Solo apunta a item_id; los datos viven en SQLite.
_cola: asyncio.Queue[str] = asyncio.Queue()
_worker_task: asyncio.Task | None = None
_worker_lock = asyncio.Lock()


# =============================================================================
# Esquema SQLite
# =============================================================================

def _conexion() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lotes (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            creado_en TEXT NOT NULL,
            iniciado_en TEXT,
            finalizado_en TEXT,
            estado TEXT NOT NULL CHECK(estado IN ('pendiente','en_proceso','finalizado','cancelado')),
            norma TEXT NOT NULL,
            modo TEXT NOT NULL,
            campos TEXT,
            idioma_salida TEXT NOT NULL,
            modelo TEXT NOT NULL,
            incognito INTEGER NOT NULL DEFAULT 0,
            agrupacion TEXT NOT NULL,
            total_items INTEGER NOT NULL DEFAULT 0,
            items_listos INTEGER NOT NULL DEFAULT 0,
            items_error INTEGER NOT NULL DEFAULT 0,
            items_cancelados INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lote_items (
            id TEXT PRIMARY KEY,
            lote_id TEXT NOT NULL,
            orden INTEGER NOT NULL,
            etiqueta TEXT,
            nombres_archivos TEXT NOT NULL,
            estado TEXT NOT NULL CHECK(estado IN ('pendiente','en_proceso','listo','error','cancelado')),
            ruta_entrada TEXT NOT NULL,
            ruta_resultado TEXT,
            intentos INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            iniciado_en TEXT,
            finalizado_en TEXT,
            FOREIGN KEY (lote_id) REFERENCES lotes(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_lote_items_lote ON lote_items(lote_id, orden)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_lote_items_estado ON lote_items(estado)")


def _db() -> sqlite3.Connection:
    conn = _conexion()
    _ensure_schema(conn)
    return conn


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# =============================================================================
# Tipos de retorno
# =============================================================================

@dataclass
class ResumenLote:
    id: str
    username: str
    estado: str
    creado_en: str
    iniciado_en: str | None
    finalizado_en: str | None
    norma: str
    modo: str
    idioma_salida: str
    modelo: str
    incognito: bool
    agrupacion: str
    total_items: int
    items_listos: int
    items_error: int
    items_cancelados: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


@dataclass
class ResumenItem:
    id: str
    orden: int
    etiqueta: str | None
    estado: str
    nombres_archivos: list[str]
    intentos: int
    error: str | None
    iniciado_en: str | None
    finalizado_en: str | None

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        return d


# =============================================================================
# Saneado de nombres y validación de ZIP
# =============================================================================

_NOMBRE_SEGURO_INVALIDO = set('\\/:*?"<>|')


def _saneo_nombre_seguro(nombre: str, max_len: int = 180) -> str:
    """Equivalente a _sanear_texto_corto de api.py para nombres de archivo."""
    if not nombre:
        return "sin_nombre"
    cleaned = []
    for ch in nombre:
        if not ch.isprintable():
            cleaned.append(" ")
        elif ch in _NOMBRE_SEGURO_INVALIDO:
            cleaned.append(" ")
        else:
            cleaned.append(ch)
    texto = " ".join("".join(cleaned).split())
    texto = texto[:max_len].strip()
    return texto or "sin_nombre"


def _extraer_zip_libro(fuente_zip: bytes | Path, destino: Path) -> list[Path]:
    """
    Extrae los ficheros de un ZIP de libro (modo un_libro_por_zip) a `destino`
    con validaciones anti-zipbomb. Devuelve la lista de rutas extraídas, en el
    orden en que aparecen en el ZIP.

    `fuente_zip` puede ser el contenido en memoria (bytes) o la ruta de un
    fichero ZIP ya guardado en disco (lo que usa crear_lote para no cargar la
    subida entera en memoria).

    No valida MIME aquí: la validación real la hace router.procesar() por cada
    archivo cuando el worker lo procesa.
    """
    origen = io.BytesIO(fuente_zip) if isinstance(fuente_zip, (bytes, bytearray)) else fuente_zip
    try:
        with zipfile.ZipFile(origen) as zf:
            infos = zf.infolist()
            if len(infos) > ZIP_MAX_ENTRADAS:
                raise ErrorValidacion(
                    f"ZIP con demasiadas entradas ({len(infos)}); máximo {ZIP_MAX_ENTRADAS}."
                )
            total_descomprimido = 0
            for inf in infos:
                if inf.is_dir():
                    continue
                if inf.file_size > ZIP_MAX_DESCOMPRIMIDO:
                    raise ErrorValidacion("Entrada de ZIP supera el tamaño descomprimido permitido.")
                total_descomprimido += inf.file_size
                if total_descomprimido > ZIP_MAX_DESCOMPRIMIDO:
                    raise ErrorValidacion("ZIP supera el tamaño descomprimido total permitido.")
                if inf.compress_size and inf.file_size / max(1, inf.compress_size) > ZIP_MAX_RATIO:
                    raise ErrorValidacion("Entrada de ZIP con ratio de compresión sospechosamente alto.")
            destino.mkdir(parents=True, exist_ok=True)
            rutas: list[Path] = []
            for idx, inf in enumerate(infos):
                if inf.is_dir():
                    continue
                base = Path(inf.filename).name  # descarta ruta interna por seguridad
                base_seguro = _saneo_nombre_seguro(base, 180)
                if not base_seguro or base_seguro.startswith("."):
                    base_seguro = f"archivo_{idx + 1}"
                destino_archivo = destino / f"{idx:03d}__{base_seguro}"
                with zf.open(inf, "r") as src, destino_archivo.open("wb") as dst:
                    leido = 0
                    while True:
                        trozo = src.read(1024 * 1024)
                        if not trozo:
                            break
                        leido += len(trozo)
                        if leido > ZIP_MAX_DESCOMPRIMIDO:
                            raise ErrorValidacion("ZIP supera el tamaño descomprimido durante la extracción.")
                        dst.write(trozo)
                rutas.append(destino_archivo)
            if not rutas:
                raise ErrorValidacion("El ZIP no contiene ficheros aprovechables.")
            return rutas
    except zipfile.BadZipFile as exc:
        raise ErrorValidacion("Archivo ZIP corrupto o no válido.") from exc


# =============================================================================
# Creación de lote
# =============================================================================

class _LimiteSubidaSuperado(Exception):
    """Una subida supera el límite del lote ("lote") o la cuota ("usuario")."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


async def _guardar_subida(fichero: UploadFile, destino: Path, limite: int, motivo: str) -> int:
    """Copia un UploadFile a `destino` por bloques de 1 MB, sin cargarlo
    entero en memoria. Lanza _LimiteSubidaSuperado(motivo) en cuanto se supera
    `limite`. Devuelve los bytes escritos."""
    if limite <= 0:
        raise _LimiteSubidaSuperado(motivo)
    escritos = 0
    await fichero.seek(0)
    with destino.open("wb") as dst:
        while True:
            trozo = await fichero.read(_TROZO_SUBIDA)
            if not trozo:
                break
            escritos += len(trozo)
            if escritos > limite:
                raise _LimiteSubidaSuperado(motivo)
            dst.write(trozo)
    return escritos


async def crear_lote(
    *,
    ficheros: list[UploadFile],
    agrupacion: str,
    norma: str,
    modo: str,
    campos: str | None,
    idioma_salida: str,
    modelo: str,
    incognito: bool,
    etiquetas: list[str] | None,
    username: str,
) -> str:
    """
    Persiste un lote nuevo y sus items, guarda los ficheros de entrada en
    /app/data/batches/<lote_id>/<item_id>/, encola los items en el worker
    y devuelve el id del lote.

    Lanza ValueError o ErrorValidacion en caso de entrada inválida; el caller
    (capa HTTP) las traduce a HTTPException con códigos apropiados.
    """
    if agrupacion not in {"un_libro_por_fichero", "un_libro_por_zip"}:
        raise ValueError(f"Agrupación no soportada: {agrupacion}")
    if not ficheros:
        raise ValueError("Debe subirse al menos un libro.")
    if len(ficheros) > MAX_LIBROS_LOTE:
        raise ValueError(f"Demasiados libros en el lote: máximo {MAX_LIBROS_LOTE}.")

    # Retención y cuota antes de aceptar nada nuevo.
    try:
        await asyncio.to_thread(purgar_lotes_caducados)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo aplicar la retención de lotes")
    uso_actual = await asyncio.to_thread(uso_disco_usuario, username)
    disponible_usuario = MAX_BYTES_USUARIO - uso_actual
    if disponible_usuario <= 0:
        raise ValueError(
            "Ha alcanzado el espacio máximo para lotes "
            f"({MAX_BYTES_USUARIO // (1024 * 1024)} MB). Borre lotes antiguos para continuar."
        )

    lote_id = uuid.uuid4().hex[:16]
    base = LOTES_DIR / lote_id
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(LOTES_DIR, 0o700)
    except OSError:
        pass

    items_a_persistir: list[tuple[str, int, str | None, list[str], Path]] = []
    bytes_subidos = 0     # lo recibido (límite MAX_BYTES_LOTE, como antes)
    bytes_en_disco = 0    # lo que queda guardado (cuota por usuario)

    try:
        for idx, fichero in enumerate(ficheros):
            nombre_base = _saneo_nombre_seguro(fichero.filename or f"libro_{idx + 1}", 180)
            etiqueta = None
            if etiquetas and idx < len(etiquetas):
                etiqueta = _saneo_nombre_seguro(etiquetas[idx], 80)
            item_id = uuid.uuid4().hex[:12]
            item_dir = base / item_id
            item_dir.mkdir(parents=True, exist_ok=True)

            # Copia por bloques: el fichero nunca se carga entero en memoria.
            restante_lote = MAX_BYTES_LOTE - bytes_subidos
            restante_usuario = disponible_usuario - bytes_en_disco
            limite_fichero = min(restante_lote, restante_usuario)
            motivo_limite = "lote" if restante_lote <= restante_usuario else "usuario"
            nombres: list[str] = []
            if agrupacion == "un_libro_por_fichero":
                destino = item_dir / f"000__{nombre_base}"
                escritos = await _guardar_subida(fichero, destino, limite_fichero, motivo_limite)
                bytes_subidos += escritos
                bytes_en_disco += escritos
                nombres.append(nombre_base)
            else:  # un_libro_por_zip
                zip_temporal = item_dir / _NOMBRE_ZIP_TEMPORAL
                try:
                    escritos = await _guardar_subida(fichero, zip_temporal, limite_fichero, motivo_limite)
                    bytes_subidos += escritos
                    try:
                        rutas = await asyncio.to_thread(_extraer_zip_libro, zip_temporal, item_dir)
                    except ErrorValidacion as exc:
                        raise ValueError(f"{nombre_base}: {exc}") from None
                finally:
                    zip_temporal.unlink(missing_ok=True)
                bytes_en_disco += sum(r.stat().st_size for r in rutas)
                if bytes_en_disco > disponible_usuario:
                    raise _LimiteSubidaSuperado("usuario")
                nombres = [r.name.split("__", 1)[1] if "__" in r.name else r.name for r in rutas]

            items_a_persistir.append((item_id, idx, etiqueta, nombres, item_dir))
    except _LimiteSubidaSuperado as exc:
        _borrar_dir(base)
        if exc.motivo == "lote":
            raise ValueError(
                f"El lote supera el tamaño máximo permitido ({MAX_BYTES_LOTE} bytes)."
            ) from None
        raise ValueError(
            "El lote no cabe en el espacio máximo para lotes de este usuario "
            f"({MAX_BYTES_USUARIO // (1024 * 1024)} MB). Borre lotes antiguos para continuar."
        ) from None
    except BaseException:
        # Cualquier otro fallo (ZIP inválido, disco lleno, cancelación): no
        # dejar ficheros a medias de un lote que no llega a existir.
        _borrar_dir(base)
        raise

    # Persistir lote + items atómicamente.
    with _db() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute(
                """
                INSERT INTO lotes (id, username, creado_en, estado, norma, modo, campos,
                                   idioma_salida, modelo, incognito, agrupacion, total_items)
                VALUES (?, ?, ?, 'pendiente', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (lote_id, username, _ahora(), norma, modo, campos, idioma_salida,
                 modelo, 1 if incognito else 0, agrupacion, len(items_a_persistir)),
            )
            for item_id, orden, etiqueta, nombres, item_dir in items_a_persistir:
                conn.execute(
                    """
                    INSERT INTO lote_items (id, lote_id, orden, etiqueta, nombres_archivos,
                                            estado, ruta_entrada, intentos)
                    VALUES (?, ?, ?, ?, ?, 'pendiente', ?, 0)
                    """,
                    (item_id, lote_id, orden, etiqueta,
                     json.dumps(nombres, ensure_ascii=False), str(item_dir)),
                )
            conn.execute("COMMIT")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            _borrar_dir(base)
            raise

    # Encolar.
    for item_id, *_ in items_a_persistir:
        await _cola.put(item_id)

    logger.info("[lote %s] creado por %s con %d libros (agrupacion=%s)",
                lote_id, username, len(items_a_persistir), agrupacion)
    return lote_id


# =============================================================================
# Consulta
# =============================================================================

def obtener_lote(lote_id: str, username: str | None = None) -> ResumenLote | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM lotes WHERE id = ?", (lote_id,)).fetchone()
    if not row:
        return None
    if username is not None and row["username"] != username:
        return None
    return ResumenLote(
        id=row["id"], username=row["username"], estado=row["estado"],
        creado_en=row["creado_en"], iniciado_en=row["iniciado_en"],
        finalizado_en=row["finalizado_en"], norma=row["norma"], modo=row["modo"],
        idioma_salida=row["idioma_salida"], modelo=row["modelo"],
        incognito=bool(row["incognito"]), agrupacion=row["agrupacion"],
        total_items=row["total_items"], items_listos=row["items_listos"],
        items_error=row["items_error"], items_cancelados=row["items_cancelados"],
    )


def listar_items(lote_id: str) -> list[ResumenItem]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM lote_items WHERE lote_id = ? ORDER BY orden ASC",
            (lote_id,),
        ).fetchall()
    items: list[ResumenItem] = []
    for r in rows:
        try:
            nombres = json.loads(r["nombres_archivos"]) if r["nombres_archivos"] else []
        except json.JSONDecodeError:
            nombres = []
        items.append(ResumenItem(
            id=r["id"], orden=r["orden"], etiqueta=r["etiqueta"], estado=r["estado"],
            nombres_archivos=nombres, intentos=r["intentos"], error=r["error"],
            iniciado_en=r["iniciado_en"], finalizado_en=r["finalizado_en"],
        ))
    return items


def leer_resultado_item(lote_id: str, item_id: str) -> dict[str, Any] | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT ruta_resultado, lote_id FROM lote_items WHERE id = ? AND lote_id = ?",
            (item_id, lote_id),
        ).fetchone()
    if not row or not row["ruta_resultado"]:
        return None
    ruta = Path(row["ruta_resultado"])
    if not ruta.is_file():
        return None
    try:
        with ruta.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def listar_lotes(username: str, limite: int = 50) -> list[ResumenLote]:
    limite = max(1, min(200, int(limite)))
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM lotes WHERE username = ? ORDER BY creado_en DESC LIMIT ?",
            (username, limite),
        ).fetchall()
    out: list[ResumenLote] = []
    for r in rows:
        out.append(ResumenLote(
            id=r["id"], username=r["username"], estado=r["estado"],
            creado_en=r["creado_en"], iniciado_en=r["iniciado_en"],
            finalizado_en=r["finalizado_en"], norma=r["norma"], modo=r["modo"],
            idioma_salida=r["idioma_salida"], modelo=r["modelo"],
            incognito=bool(r["incognito"]), agrupacion=r["agrupacion"],
            total_items=r["total_items"], items_listos=r["items_listos"],
            items_error=r["items_error"], items_cancelados=r["items_cancelados"],
        ))
    return out


# =============================================================================
# Cancelación y borrado
# =============================================================================

def cancelar_lote(lote_id: str, username: str) -> bool:
    """Marca como cancelado el lote y los items pendientes. No interrumpe el
    item en curso para no dejar a Ollama o al sandbox en estado inconsistente."""
    with _db() as conn:
        row = conn.execute(
            "SELECT username, estado FROM lotes WHERE id = ?", (lote_id,)
        ).fetchone()
        if not row or row["username"] != username:
            return False
        if row["estado"] in {"finalizado", "cancelado"}:
            return False
        conn.execute("BEGIN")
        try:
            res = conn.execute(
                "UPDATE lote_items SET estado='cancelado', finalizado_en=? "
                "WHERE lote_id=? AND estado='pendiente'",
                (_ahora(), lote_id),
            )
            cancelados = res.rowcount or 0
            conn.execute(
                "UPDATE lotes SET items_cancelados = items_cancelados + ?, estado=?, "
                "finalizado_en=COALESCE(finalizado_en, ?) WHERE id=?",
                (cancelados, "cancelado", _ahora(), lote_id),
            )
            conn.execute("COMMIT")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            raise
    logger.info("[lote %s] cancelado por %s (%d items pendientes anulados)",
                lote_id, username, cancelados)
    return True


def borrar_lote(lote_id: str, username: str) -> bool:
    with _db() as conn:
        row = conn.execute(
            "SELECT username, estado FROM lotes WHERE id = ?", (lote_id,)
        ).fetchone()
        if not row or row["username"] != username:
            return False
        if row["estado"] in {"pendiente", "en_proceso"}:
            return False  # forzar cancelación previa
        conn.execute("DELETE FROM lotes WHERE id = ?", (lote_id,))
        conn.execute("DELETE FROM lote_items WHERE lote_id = ?", (lote_id,))
    _borrar_dir(LOTES_DIR / lote_id)
    logger.info("[lote %s] borrado por %s", lote_id, username)
    return True


def _borrar_dir(path: Path) -> None:
    if not path.exists():
        return
    try:
        import shutil
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo borrar el directorio %s", path)


# =============================================================================
# Almacenamiento: cuota, retención, originales y borrado por usuario
# =============================================================================

def _bytes_en_disco(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for raiz, _dirs, ficheros in os.walk(path):
        for nombre in ficheros:
            try:
                total += (Path(raiz) / nombre).stat().st_size
            except OSError:
                pass
    return total


def uso_disco_usuario(username: str) -> int:
    """Bytes que ocupan en disco todos los lotes de `username`."""
    if not DB_PATH.exists():
        return 0
    with _db() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM lotes WHERE username = ?", (username,))]
    return sum(_bytes_en_disco(LOTES_DIR / lote_id) for lote_id in ids)


def _borrar_lotes(ids: list[str]) -> None:
    """Borra lotes (filas e items) y sus directorios. Sin comprobar dueño."""
    if not ids:
        return
    with _db() as conn:
        conn.execute("BEGIN")
        try:
            for lote_id in ids:
                conn.execute("DELETE FROM lote_items WHERE lote_id = ?", (lote_id,))
                conn.execute("DELETE FROM lotes WHERE id = ?", (lote_id,))
            conn.execute("COMMIT")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            raise
    for lote_id in ids:
        _borrar_dir(LOTES_DIR / lote_id)


def borrar_lotes_de_usuario(username: str) -> int:
    """Borra todos los lotes de `username`, en cualquier estado, con sus
    documentos y resultados. Lo usa auth al eliminar un usuario y antes de
    crear uno con un nombre que pudo existir: así nadie hereda lotes ajenos.

    Si un item de esos lotes se está procesando en ese momento, el worker lo
    termina sin efecto: su fila ya no existe y su directorio tampoco.
    Devuelve el número de lotes borrados."""
    if not DB_PATH.exists():
        return 0  # nunca se ha creado ningún lote
    with _db() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM lotes WHERE username = ?", (username,))]
    _borrar_lotes(ids)
    if ids:
        logger.info("Borrados %d lotes del usuario %s", len(ids), username)
    return len(ids)


def purgar_lotes_caducados() -> int:
    """Aplica TIPO_LOTE_RETENCION_DIAS: borra lotes finalizados o cancelados
    cuya finalización (o creación) sea anterior al plazo. Los lotes pendientes
    o en proceso nunca se tocan. Devuelve el número de lotes borrados."""
    if RETENCION_DIAS <= 0 or not DB_PATH.exists():
        return 0
    corte = (datetime.now() - timedelta(days=RETENCION_DIAS)).isoformat(timespec="seconds")
    with _db() as conn:
        ids = [
            r["id"] for r in conn.execute(
                "SELECT id FROM lotes WHERE estado IN ('finalizado', 'cancelado') "
                "AND COALESCE(finalizado_en, creado_en) < ?",
                (corte,),
            )
        ]
    _borrar_lotes(ids)
    if ids:
        logger.info("Retención: borrados %d lotes con más de %d días", len(ids), RETENCION_DIAS)
    return len(ids)


def _borrar_originales_de_dir(item_dir: Path) -> None:
    """Borra los ficheros de entrada de un item y conserva result.json."""
    if not item_dir.is_dir():
        return
    for ruta in item_dir.iterdir():
        if ruta.is_file() and ruta.name != "result.json":
            try:
                ruta.unlink()
            except OSError:
                logger.warning("No se pudo borrar el original %s", ruta)


def limpiar_originales_si_procede(item_id: str) -> None:
    """Tras procesar un item: si ha terminado (listo, error o cancelado) y el
    lote es incógnito o CONSERVAR_ORIGINALES está desactivado, borra sus
    documentos originales. El resultado (result.json) se conserva."""
    with _db() as conn:
        row = conn.execute(
            "SELECT i.estado, i.ruta_entrada, l.incognito FROM lote_items i "
            "JOIN lotes l ON l.id = i.lote_id WHERE i.id = ?",
            (item_id,),
        ).fetchone()
    if not row or row["estado"] not in {"listo", "error", "cancelado"}:
        return
    if CONSERVAR_ORIGINALES and not row["incognito"]:
        return
    _borrar_originales_de_dir(Path(row["ruta_entrada"]))


def limpiar_originales_finalizados() -> int:
    """Al arrancar: aplica la misma regla a items terminados antes de esta
    versión o de un reinicio. Devuelve cuántos items se han revisado."""
    condicion = "" if not CONSERVAR_ORIGINALES else "AND l.incognito = 1"
    with _db() as conn:
        rows = conn.execute(
            "SELECT i.ruta_entrada FROM lote_items i JOIN lotes l ON l.id = i.lote_id "
            f"WHERE i.estado IN ('listo', 'error', 'cancelado') {condicion}"
        ).fetchall()
    for r in rows:
        _borrar_originales_de_dir(Path(r["ruta_entrada"]))
    return len(rows)


# =============================================================================
# Worker
# =============================================================================

async def iniciar_worker_si_inactivo() -> None:
    """Garantiza un único worker vivo. Idempotente: llámalo en lifespan."""
    global _worker_task
    async with _worker_lock:
        if _worker_task is None or _worker_task.done():
            _worker_task = asyncio.create_task(_bucle_worker(), name="tipo-lote-worker")
            logger.info("Worker de lotes iniciado")


async def detener_worker() -> None:
    global _worker_task
    async with _worker_lock:
        if _worker_task and not _worker_task.done():
            _worker_task.cancel()
            try:
                await _worker_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        _worker_task = None


def recuperar_arranque() -> None:
    """Devuelve a 'pendiente' los items que quedaron 'en_proceso' por un
    reinicio brusco, salvo que ya superen el límite de reintentos. Reencola
    todos los pendientes. Llámalo una sola vez al arrancar antes del worker."""
    with _db() as conn:
        # Items huérfanos en_proceso → pendiente con un intento más, o error si superan.
        en_proceso = conn.execute(
            "SELECT id, intentos FROM lote_items WHERE estado='en_proceso'"
        ).fetchall()
        for r in en_proceso:
            nuevos_intentos = (r["intentos"] or 0) + 1
            if nuevos_intentos > REINTENTOS_MAX:
                conn.execute(
                    "UPDATE lote_items SET estado='error', intentos=?, error=?, finalizado_en=? "
                    "WHERE id=?",
                    (nuevos_intentos, "Reinicio del servicio durante el procesamiento; "
                     "máximo de reintentos superado.", _ahora(), r["id"]),
                )
            else:
                conn.execute(
                    "UPDATE lote_items SET estado='pendiente', intentos=?, iniciado_en=NULL "
                    "WHERE id=?",
                    (nuevos_intentos, r["id"]),
                )

        # Recalcular agregados de lotes afectados y dejarlos en 'pendiente' si tienen
        # algún item pendiente, o finalizarlos si ya no.
        _reconciliar_agregados(conn)

        pendientes = conn.execute(
            "SELECT id FROM lote_items WHERE estado='pendiente' "
            "ORDER BY (SELECT creado_en FROM lotes WHERE lotes.id = lote_items.lote_id), orden"
        ).fetchall()
    for r in pendientes:
        _cola.put_nowait(r["id"])
    logger.info("Recuperación de arranque: %d items pendientes reencolados", len(pendientes))

    # Mantenimiento de almacenamiento (auditoría 2026-10). Errores aquí no
    # deben impedir que el worker arranque.
    try:
        purgar_lotes_caducados()
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo aplicar la retención de lotes al arrancar")
    try:
        limpiar_originales_finalizados()
    except Exception:  # noqa: BLE001
        logger.exception("No se pudieron limpiar originales de items terminados al arrancar")


def _reconciliar_agregados(conn: sqlite3.Connection) -> None:
    """Recalcula items_listos/error/cancelados y el estado del lote en base a
    sus items. Útil tras la recuperación de arranque."""
    rows = conn.execute("SELECT id FROM lotes").fetchall()
    for r in rows:
        lote_id = r["id"]
        agg = conn.execute(
            """
            SELECT
              SUM(CASE WHEN estado='listo' THEN 1 ELSE 0 END) AS listos,
              SUM(CASE WHEN estado='error' THEN 1 ELSE 0 END) AS errores,
              SUM(CASE WHEN estado='cancelado' THEN 1 ELSE 0 END) AS cancelados,
              SUM(CASE WHEN estado='pendiente' THEN 1 ELSE 0 END) AS pendientes,
              SUM(CASE WHEN estado='en_proceso' THEN 1 ELSE 0 END) AS en_proceso,
              COUNT(*) AS total
            FROM lote_items WHERE lote_id = ?
            """,
            (lote_id,),
        ).fetchone()
        listos = agg["listos"] or 0
        errores = agg["errores"] or 0
        cancelados = agg["cancelados"] or 0
        pendientes = agg["pendientes"] or 0
        en_proceso = agg["en_proceso"] or 0
        nuevo_estado: str
        if pendientes or en_proceso:
            nuevo_estado = "pendiente"
        elif (listos + errores + cancelados) > 0:
            nuevo_estado = "cancelado" if cancelados and not listos and not errores else "finalizado"
        else:
            nuevo_estado = "pendiente"
        conn.execute(
            "UPDATE lotes SET items_listos=?, items_error=?, items_cancelados=?, estado=? "
            "WHERE id=?",
            (listos, errores, cancelados, nuevo_estado, lote_id),
        )


async def _bucle_worker() -> None:
    """Bucle principal: coge un item_id de la cola, lo procesa, y vuelve."""
    while True:
        try:
            item_id = await _cola.get()
        except asyncio.CancelledError:
            raise
        try:
            await _procesar_item(item_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Fallo inesperado en el worker procesando item %s", item_id)
        finally:
            try:
                await asyncio.to_thread(limpiar_originales_si_procede, item_id)
            except Exception:  # noqa: BLE001
                logger.exception("No se pudieron limpiar los originales del item %s", item_id)
            _cola.task_done()


async def _procesar_item(item_id: str) -> None:
    """Procesa un único item. Reusa router.procesar + extractor.extraer."""
    # 1. Cargar item y lote
    with _db() as conn:
        item = conn.execute(
            "SELECT * FROM lote_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            return
        lote = conn.execute(
            "SELECT * FROM lotes WHERE id = ?", (item["lote_id"],)
        ).fetchone()
        if not lote:
            return
        # Si el lote o el item están cancelados, salir.
        if lote["estado"] == "cancelado" or item["estado"] in {"cancelado", "listo"}:
            return
        # Marcar item en_proceso
        conn.execute(
            "UPDATE lote_items SET estado='en_proceso', iniciado_en=? WHERE id=?",
            (_ahora(), item_id),
        )
        # Marcar lote en_proceso (si no lo está)
        if lote["estado"] == "pendiente":
            conn.execute(
                "UPDATE lotes SET estado='en_proceso', iniciado_en=COALESCE(iniciado_en, ?) "
                "WHERE id=?",
                (_ahora(), lote["id"]),
            )

    # 2. Cargar ficheros del item desde disco
    item_dir = Path(item["ruta_entrada"])
    if not item_dir.is_dir():
        await _marcar_error(item_id, "Directorio del item no encontrado.")
        return
    ficheros = sorted(item_dir.iterdir(), key=lambda p: p.name)
    ficheros = [p for p in ficheros if p.is_file() and p.name != "result.json"]
    if not ficheros:
        await _marcar_error(item_id, "El item no contiene ficheros.")
        return

    # 3. Cargar esquema según norma del lote
    DIR_ESQUEMAS = Path(os.getenv("DIR_ESQUEMAS", "/app/schemas"))
    PERFILES_DISPONIBLES = {"marc21-monografias": "datos-bibliograficos-monografia.yaml"}
    archivo_esquema = PERFILES_DISPONIBLES.get(lote["norma"])
    if not archivo_esquema:
        await _marcar_error(item_id, f"Norma desconocida: {lote['norma']}")
        return
    try:
        esquema = extractor.cargar_esquema(DIR_ESQUEMAS / archivo_esquema)
    except (FileNotFoundError, ValueError) as exc:
        await _marcar_error(item_id, f"No se pudo cargar el esquema: {exc}")
        return

    # 4. Procesar cada fichero del item (sandbox + zonas) en thread → no bloquea event loop
    INCLUIR_HASH = os.getenv("INCLUIR_HASH_DOCUMENTO_AUDITORIA", "true").strip().lower() in VALORES_TRUE
    procesados: list[tuple[router_entrada.DocumentoProcesado, str, str | None]] = []
    from .api import comprobar_presupuesto_imagenes  # importación tardía (como abajo)
    bytes_imagenes_acumulados = 0
    try:
        for idx, ruta in enumerate(ficheros):
            contenido = await asyncio.to_thread(ruta.read_bytes)
            sha256 = hashlib.sha256(contenido).hexdigest() if INCLUIR_HASH else None
            nombre_real = ruta.name.split("__", 1)[1] if "__" in ruta.name else ruta.name
            etiqueta = item["etiqueta"] or f"imagen_{idx + 1}"
            try:
                doc = await asyncio.to_thread(router_entrada.procesar, contenido, nombre_real)
                # Un ZIP de libro puede traer hasta 60 ficheros: mismo
                # presupuesto global de imágenes que /api/describir.
                bytes_imagenes_acumulados = comprobar_presupuesto_imagenes(bytes_imagenes_acumulados, doc)
            except ErrorValidacion as exc:
                await _marcar_error(item_id, f"{nombre_real}: {exc}")
                return
            procesados.append((doc, etiqueta, sha256))
            contenido = b""
    except Exception as exc:  # noqa: BLE001
        await _marcar_error(item_id, f"Error procesando ficheros del item: {exc}")
        return

    # 5. Fusionar y extraer (bajo el mismo semáforo global que /api/describir)
    try:
        from .api import _fusionar_documentos, _construir_filtro, _SEM_PROCESAMIENTO  # importación tardía
        conjunto = _fusionar_documentos(procesados)
        filtro = _construir_filtro_seguro(lote["modo"], lote["campos"], esquema, _construir_filtro)
    except Exception as exc:  # noqa: BLE001
        await _marcar_error(item_id, f"Error preparando extracción: {exc}")
        return

    async with _SEM_PROCESAMIENTO:
        # Comprobar cancelación tardía
        if _esta_cancelado(item["lote_id"]):
            await _marcar_cancelado(item_id)
            return
        try:
            propuesta = await extractor.extraer(
                conjunto.entrada, esquema, lote["modelo"], filtro, lote["idioma_salida"]
            )
            bibliografico.aplicar_validaciones(propuesta)
            bibliografico.aplicar_bloques_isbd_a_propuesta(propuesta)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[lote %s item %s] error en extracción", item["lote_id"], item_id)
            await _marcar_error(item_id, f"Error en la extracción: {exc}")
            return

    # 6. Construir payload de resultado idéntico al de /api/describir
    try:
        ficha = auditoria.generar_ficha_tecnica(
            peticion_id=item_id,
            documento=conjunto,
            esquema=esquema,
            modo=lote["modo"],
            idioma_salida=lote["idioma_salida"],
            modelo=lote["modelo"],
            filtro_claves=filtro,
            propuesta=propuesta,
            deteccion=None,
            sha256_documento=None,
            incognito=bool(lote["incognito"]),
        )
        campos_dict = [c.__dict__ for c in propuesta.campos]
        isbd = bibliografico.generar_isbd_desde_campos(campos_dict)
        from . import exportadores as _exp
        marc21_lineas = _exp.generar_marc21_texto(campos_dict, lote["idioma_salida"])
        marc21_texto = _exp.marc21_a_texto_plano(marc21_lineas)
        payload = {
            "peticion": item_id,
            "lote_id": item["lote_id"],
            "idioma_salida": lote["idioma_salida"],
            "modelo": lote["modelo"],
            "version_tipo": APP_VERSION,
            "documento": {
                "nombre": conjunto.nombre_original,
                "tipo_mime": conjunto.tipo_mime,
                "tamano_bytes": conjunto.tamano_bytes,
                "paginas": conjunto.paginas,
                "ruta_procesamiento": conjunto.ruta,
                "archivos": [a.__dict__ for a in conjunto.archivos],
                "cobertura_zonas": conjunto.cobertura,
            },
            "auditoria": ficha,
            "isbd": isbd,
            "marc21_lineas": marc21_lineas,
            "marc21_texto": marc21_texto,
            "propuesta": propuesta.to_dict(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[lote %s item %s] error preparando resultado", item["lote_id"], item_id)
        await _marcar_error(item_id, f"Error preparando resultado: {exc}")
        return

    # 7. Persistir resultado y marcar listo
    ruta_resultado = item_dir / "result.json"
    try:
        tmp = ruta_resultado.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, ruta_resultado)
        try:
            ruta_resultado.chmod(0o600)
        except OSError:
            pass
    except OSError as exc:
        await _marcar_error(item_id, f"No se pudo guardar el resultado: {exc}")
        return

    await _marcar_listo(item_id, str(ruta_resultado))


def _construir_filtro_seguro(
    modo: str, campos_str: str | None, esquema: Any, fn_filtro
) -> set[str] | None:
    """Wrapper para reutilizar _construir_filtro de api.py atrapando HTTPException."""
    from fastapi import HTTPException
    try:
        return fn_filtro(modo, campos_str, esquema)
    except HTTPException as exc:
        raise RuntimeError(exc.detail) from None


def _esta_cancelado(lote_id: str) -> bool:
    with _db() as conn:
        row = conn.execute("SELECT estado FROM lotes WHERE id = ?", (lote_id,)).fetchone()
    return bool(row and row["estado"] == "cancelado")


async def _marcar_listo(item_id: str, ruta_resultado: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE lote_items SET estado='listo', ruta_resultado=?, finalizado_en=?, error=NULL "
            "WHERE id=?",
            (ruta_resultado, _ahora(), item_id),
        )
        conn.execute(
            "UPDATE lotes SET items_listos = items_listos + 1 "
            "WHERE id = (SELECT lote_id FROM lote_items WHERE id = ?)",
            (item_id,),
        )
        _finalizar_lote_si_procede(conn, item_id)


async def _marcar_error(item_id: str, mensaje: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE lote_items SET estado='error', error=?, finalizado_en=? WHERE id=?",
            (mensaje[:2000], _ahora(), item_id),
        )
        conn.execute(
            "UPDATE lotes SET items_error = items_error + 1 "
            "WHERE id = (SELECT lote_id FROM lote_items WHERE id = ?)",
            (item_id,),
        )
        _finalizar_lote_si_procede(conn, item_id)
    logger.warning("[item %s] error: %s", item_id, mensaje)


async def _marcar_cancelado(item_id: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE lote_items SET estado='cancelado', finalizado_en=? WHERE id=?",
            (_ahora(), item_id),
        )
        conn.execute(
            "UPDATE lotes SET items_cancelados = items_cancelados + 1 "
            "WHERE id = (SELECT lote_id FROM lote_items WHERE id = ?)",
            (item_id,),
        )
        _finalizar_lote_si_procede(conn, item_id)


def _finalizar_lote_si_procede(conn: sqlite3.Connection, item_id: str) -> None:
    row = conn.execute(
        """
        SELECT l.id, l.total_items, l.items_listos, l.items_error, l.items_cancelados, l.estado
        FROM lote_items i JOIN lotes l ON l.id = i.lote_id
        WHERE i.id = ?
        """,
        (item_id,),
    ).fetchone()
    if not row:
        return
    completados = (row["items_listos"] or 0) + (row["items_error"] or 0) + (row["items_cancelados"] or 0)
    if completados >= (row["total_items"] or 0):
        # Si todos cancelados → estado cancelado; si no, finalizado.
        if (row["items_cancelados"] or 0) == (row["total_items"] or 0):
            nuevo = "cancelado"
        else:
            nuevo = "finalizado"
        conn.execute(
            "UPDATE lotes SET estado=?, finalizado_en=COALESCE(finalizado_en, ?) WHERE id=?",
            (nuevo, _ahora(), row["id"]),
        )
        logger.info("[lote %s] %s (listos=%d errores=%d cancelados=%d)",
                    row["id"], nuevo, row["items_listos"], row["items_error"], row["items_cancelados"])
