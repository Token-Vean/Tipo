"""
Directorio de ficheros temporales de Tipo.

Starlette guarda en disco los ficheros que llegan por multipart en cuanto
superan 1 MB, usando el directorio temporal por defecto de Python. En el
contenedor, /tmp es un tmpfs de 512 MB que vive en RAM y cuenta contra el
límite de memoria del servicio: un lote grande lo llenaba (error confuso) o
empujaba el contenedor hacia el límite de memoria mientras el sandbox de
parsers también reservaba la suya.

Desde 0.3.1 docker-compose.yml fija TMPDIR=/app/data/tmp, dentro del
volumen persistente. Este módulo crea ese directorio con permisos 0700 al
arrancar y borra restos de una ejecución anterior (por ejemplo, tras un
corte brusco a mitad de una subida). Solo vacía el directorio si cuelga
directamente del directorio de datos de Tipo y se llama `tmp`, para no
borrar nada si TMPDIR apunta por error a otro sitio.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def preparar_directorio_temporal() -> Path | None:
    ruta_env = os.getenv("TMPDIR", "").strip()
    if not ruta_env:
        return None
    ruta = Path(ruta_env)
    datos = Path(os.getenv("TIPO_DATA_DIR", "/app/data"))
    try:
        ruta.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            ruta.chmod(0o700)
        except OSError:
            pass
        es_propio = ruta.name == "tmp" and ruta.resolve().parent == datos.resolve()
        if es_propio:
            for hijo in ruta.iterdir():
                try:
                    if hijo.is_dir() and not hijo.is_symlink():
                        shutil.rmtree(hijo, ignore_errors=True)
                    else:
                        hijo.unlink(missing_ok=True)
                except OSError:
                    logger.warning("No se pudo borrar el temporal antiguo %s", hijo.name)
        else:
            logger.warning(
                "TMPDIR=%s no es el directorio temporal propio de Tipo; no se vacía.", ruta
            )
    except OSError:
        logger.exception("No se pudo preparar TMPDIR=%s; se usará el temporal del sistema", ruta)
        os.environ.pop("TMPDIR", None)
    # tempfile cachea el directorio en la primera llamada: se fuerza a
    # recalcularlo con el TMPDIR ya preparado (o sin él, si falló).
    tempfile.tempdir = None
    return Path(tempfile.gettempdir())
