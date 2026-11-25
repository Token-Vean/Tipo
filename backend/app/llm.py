"""
Cliente Ollama para Tipo.

El diseño presupone procesamiento local. Por defecto solo se permite conectar
con Ollama en loopback, host.docker.internal o el servicio Docker interno
"ollama". Si se quiere usar un endpoint remoto, debe declararse explícitamente
ALLOW_REMOTE_OLLAMA=true, porque eso puede enviar texto e imágenes de los
documentos fuera del equipo.
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import math
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from .http_local import cliente_local

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Configuración
# -----------------------------------------------------------------------------

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
ALLOW_REMOTE_OLLAMA = os.getenv("ALLOW_REMOTE_OLLAMA", "false").strip().lower() in {
    "1", "true", "yes", "si", "sí", "on",
}
TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
# Consulta de metadatos del modelo (/api/show) previa a cada inferencia. Es una
# llamada local y ligera: un timeout corto evita que bloquee la petición.
TIMEOUT_VERIFICACION_MODELO = httpx.Timeout(15.0, connect=5.0)
NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "8192"))
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))

_HOSTS_LOCALES_PERMITIDOS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "host.docker.internal",
    "ollama",  # nombre del servicio en la red interna de Docker Compose
}


def _validar_ollama_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in {"http", "https"} or not p.netloc:
        raise RuntimeError(
            "OLLAMA_URL debe ser una URL HTTP/HTTPS válida, por ejemplo "
            "http://localhost:11434."
        )
    if p.username or p.password:
        raise RuntimeError("OLLAMA_URL no debe incluir credenciales embebidas.")

    host = (p.hostname or "").lower()
    if ALLOW_REMOTE_OLLAMA:
        logger.warning(
            "ALLOW_REMOTE_OLLAMA=true: el contenido documental puede enviarse a %s", url
        )
        return

    if host in _HOSTS_LOCALES_PERMITIDOS:
        return

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise RuntimeError(
            "OLLAMA_URL apunta a un host no local. Por seguridad, esta herramienta "
            "solo permite Ollama local salvo que defina ALLOW_REMOTE_OLLAMA=true."
        ) from None

    if ip.is_loopback:
        return

    raise RuntimeError(
        "OLLAMA_URL apunta a una IP no local. Esto puede exfiltrar documentos. "
        "Use un Ollama local o defina ALLOW_REMOTE_OLLAMA=true bajo su responsabilidad."
    )


_validar_ollama_url(OLLAMA_URL)

# -----------------------------------------------------------------------------
# Versión mínima de Ollama
# -----------------------------------------------------------------------------
# CVE-2026-103663 (CERT Polska, intervalo ampliado el 17-11-2026): path
# traversal en /api/pull que permite escribir fuera del almacén de modelos y,
# en la imagen Docker oficial, ejecutar código como root al reiniciar. Afecta a
# todas las versiones anteriores a 0.35.0. Tipo reutiliza el Ollama del equipo
# cuando lo hay (perfil external): un motor vulnerable deja de ser aceptable
# aunque no sea Tipo quien lo expone. Las versiones antiguas tampoco garantizan
# los metadatos remote_host/remote_model en los que se apoya la comprobación de
# modelo local. Mismo valor que VERSION_MINIMA_OLLAMA en PlumA; debe coincidir
# con tools/windows/Tipo-Control.ps1, instalar.bat e instalar.sh
# (tests/test_revision_2026_11_unidad.py lo comprueba). Subirlo cuando un aviso
# nuevo lo requiera.
VERSION_MINIMA_OLLAMA: tuple[int, int, int] = (0, 35, 0)
_PATRON_VERSION = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)")
PERFIL = os.getenv("PERFIL", "bundled").strip().lower()


def parsear_version(texto: object) -> tuple[int, int, int] | None:
    """Convierte «0.40.17», «v0.35.0» o «0.40.17-rc3» en una tupla comparable."""
    if not isinstance(texto, str):
        return None
    coincidencia = _PATRON_VERSION.match(texto)
    if not coincidencia:
        return None
    return tuple(int(parte) for parte in coincidencia.groups())  # type: ignore[return-value]


def texto_version(version: tuple[int, ...]) -> str:
    return ".".join(str(parte) for parte in version)


async def verificar_version_ollama() -> str:
    """Falla cerrado si Ollama no informa de su versión o es anterior a la mínima.

    Se llama al arrancar (bootstrap) y antes de cada inferencia: si el usuario
    sustituye su Ollama por uno antiguo con Tipo encendido, no se le envía
    ningún documento. Devuelve la versión como texto.
    """
    minima = texto_version(VERSION_MINIMA_OLLAMA)
    try:
        async with cliente_local(TIMEOUT_VERIFICACION_MODELO) as cliente:
            resp = await cliente.get(f"{OLLAMA_URL}/api/version")
        datos = resp.json() if resp.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        datos = None
    version = parsear_version(datos.get("version") if isinstance(datos, dict) else None)

    if PERFIL == "external":
        remedio = (
            f"Actualice Ollama en este equipo a la versión {minima} o posterior "
            "(https://ollama.com/download), reinícielo y vuelva a iniciar Tipo."
        )
    else:
        remedio = (
            "Vuelva a ejecutar el instalador de esta versión de Tipo para actualizar "
            "el contenedor de Ollama."
        )
    if version is None:
        raise RuntimeError(
            "No se pudo comprobar la versión de Ollama (/api/version no responde o no "
            f"devuelve una versión reconocible). Tipo requiere Ollama {minima} o "
            f"posterior. {remedio}"
        )
    if version < VERSION_MINIMA_OLLAMA:
        raise RuntimeError(
            f"Ollama {texto_version(version)} está afectado por un aviso de seguridad "
            f"(CVE-2026-103663). Tipo requiere Ollama {minima} o posterior. {remedio}"
        )
    return texto_version(version)


def es_modelo_cloud(nombre: str) -> bool:
    """Detecta etiquetas de Ollama que delegan la inferencia en su servicio cloud."""
    n = (nombre or "").strip().lower()
    if ":" not in n:
        return False
    tag = n.rsplit(":", 1)[1]
    return tag == "cloud" or tag.endswith("-cloud")


def validar_modelo_local(nombre: str) -> None:
    if es_modelo_cloud(nombre):
        raise RuntimeError(
            "Tipo está configurado para procesamiento local y rechaza modelos cloud de Ollama "
            f"({nombre}). Seleccione un modelo descargado que no use una etiqueta :cloud."
        )


# Campos con los que Ollama declara que un modelo es remoto: su inferencia no
# se ejecuta en este equipo, sino en el host indicado (Ollama Cloud u otro).
# Aparecen tanto en cada entrada de /api/tags como en la respuesta de /api/show.
_CAMPOS_MODELO_REMOTO = ("remote_host", "remote_model")


def es_entrada_remota(entrada: Any) -> bool:
    """True si los metadatos de Ollama declaran el modelo como remoto.

    La etiqueta ``:cloud`` es solo una convención de nombre: ``ollama cp
    modelo:cloud mi-modelo`` produce un modelo sin esa etiqueta que sigue
    enviando el texto a un servidor externo. Los campos ``remote_host`` y
    ``remote_model`` acompañan al modelo aunque se renombre.
    """
    if not isinstance(entrada, dict):
        return False
    return any(str(entrada.get(campo) or "").strip() for campo in _CAMPOS_MODELO_REMOTO)


async def verificar_modelo_local(nombre: str) -> None:
    """Comprueba en Ollama, antes de enviar ningún documento, que el modelo es local.

    Falla cerrado: si Ollama no confirma que el modelo es local (error HTTP,
    respuesta ilegible o metadatos de modelo remoto), no se hace la inferencia.
    Se consulta en cada llamada, sin caché, para que sustituir un modelo ya
    comprobado por uno remoto con el mismo nombre no pase inadvertido.
    """
    validar_modelo_local(nombre)
    try:
        async with cliente_local(TIMEOUT_VERIFICACION_MODELO) as cliente:
            resp = await cliente.post(f"{OLLAMA_URL}/api/show", json={"model": nombre})
    except httpx.HTTPError as err:
        raise RuntimeError(
            f"No se pudo comprobar en Ollama que el modelo {nombre} es local "
            "(/api/show no responde). No se envía el documento."
        ) from err
    if resp.status_code != 200:
        raise RuntimeError(
            f"No se pudo comprobar en Ollama que el modelo {nombre} es local "
            f"(/api/show devolvió HTTP {resp.status_code}). No se envía el documento."
        )
    try:
        datos = resp.json()
    except ValueError as err:
        raise RuntimeError(
            f"No se pudo comprobar en Ollama que el modelo {nombre} es local "
            "(respuesta ilegible de /api/show). No se envía el documento."
        ) from err
    if not isinstance(datos, dict):
        raise RuntimeError(
            f"No se pudo comprobar en Ollama que el modelo {nombre} es local "
            "(respuesta inesperada de /api/show). No se envía el documento."
        )
    if es_entrada_remota(datos):
        raise RuntimeError(
            "Tipo está configurado para procesamiento local y rechaza modelos remotos de Ollama: "
            f"{nombre} delega la inferencia en un servidor externo, aunque su nombre no lleve "
            "la etiqueta :cloud. Seleccione un modelo descargado en este equipo."
        )


# -----------------------------------------------------------------------------
# Llamadas al modelo
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Presupuesto de la ventana de contexto
# -----------------------------------------------------------------------------
# Cuando el prompt supera num_ctx, Ollama no devuelve error: descarta el
# PRINCIPIO del prompt y responde 200 OK. En Tipo el principio son las
# instrucciones, las reglas ISBD y la lista de campos; sin ellas la propuesta
# sale degradada o vacía. Con un num_ctx fijo de 32 768 y un PDF denso esto
# podía pasar en silencio: el prompt sin documento ya ocupa ~10 000 tokens y
# se reservan NUM_PREDICT para la respuesta.
#
# Sin el tokenizador del modelo, el presupuesto es una estimación por
# caracteres (como en PlumA):
#   1. Antes de llamar: si el texto de las zonas no cabe, el extractor envía
#      su principio y su final con una marca de omisión explícita.
#   2. num_ctx se ajusta al tamaño real en tramos fijos (pocos tramos, para
#      que Ollama no recargue el modelo en cada petición) y nunca supera
#      OLLAMA_NUM_CTX, que pasa a ser el máximo. Un documento pequeño usa
#      menos memoria; uno grande ya no se trunca.
#   3. Después de llamar: Ollama informa de prompt_eval_count y eval_count; si
#      revelan truncado, el extractor lo avisa en la propuesta.


def _float_env(nombre: str, defecto: float, minimo: float, maximo: float) -> float:
    try:
        valor = float(os.getenv(nombre, str(defecto)))
    except ValueError:
        return defecto
    return max(minimo, min(maximo, valor))


CARACTERES_POR_TOKEN = _float_env("TIPO_CARACTERES_POR_TOKEN", 3.5, 2.0, 6.0)
TOKENS_POR_IMAGEN = max(64, int(os.getenv("TIPO_TOKENS_POR_IMAGEN", "600")))
MARGEN_PLANTILLA_TOKENS = 512
MIN_CARACTERES_DOCUMENTO = 2000
TRAMOS_NUM_CTX = (16384, 24576, 32768, 49152, 65536, 98304, 131072)


def tokens_necesarios(caracteres_prompt: int, imagenes: int = 0) -> int:
    """Tokens estimados de prompt + imágenes + respuesta + margen."""
    return (
        math.ceil(max(0, caracteres_prompt) / CARACTERES_POR_TOKEN)
        + max(0, imagenes) * TOKENS_POR_IMAGEN
        + NUM_PREDICT
        + MARGEN_PLANTILLA_TOKENS
    )


def num_ctx_para(caracteres_prompt: int, imagenes: int = 0) -> int:
    """Menor tramo de num_ctx en el que cabe la petición, sin pasar de NUM_CTX."""
    necesario = tokens_necesarios(caracteres_prompt, imagenes)
    candidatos = [t for t in TRAMOS_NUM_CTX if t < NUM_CTX] + [NUM_CTX]
    for tramo in candidatos:
        if tramo >= necesario:
            return tramo
    return NUM_CTX


def caracteres_documento_disponibles(caracteres_resto: int, imagenes: int = 0) -> int:
    """Caracteres de documento que caben en NUM_CTX junto al resto del prompt
    (`caracteres_resto`), las imágenes y la reserva para la respuesta."""
    libres = NUM_CTX - tokens_necesarios(caracteres_resto, imagenes)
    return max(MIN_CARACTERES_DOCUMENTO, int(libres * CARACTERES_POR_TOKEN))


def evaluar_contexto(diagnostico: dict[str, Any] | None) -> str | None:
    """Interpreta las métricas de Ollama de una llamada.

    "prompt_truncado": el prompt no cabía y Ollama descartó su principio.
    "contexto_agotado": prompt + respuesta superaron la ventana.
    "limite_salida": la respuesta alcanzó num_predict y puede estar incompleta.
    """
    if not diagnostico:
        return None

    def _entero(valor: Any) -> int:
        try:
            return int(valor or 0)
        except (TypeError, ValueError):
            return 0

    num_ctx = _entero(diagnostico.get("num_ctx"))
    num_predict = _entero(diagnostico.get("num_predict"))
    prompt = _entero(diagnostico.get("prompt_eval_count"))
    salida = _entero(diagnostico.get("eval_count"))
    if num_ctx > 0 and prompt >= num_ctx:
        return "prompt_truncado"
    if num_ctx > 0 and prompt > 0 and prompt + salida > num_ctx:
        return "contexto_agotado"
    if diagnostico.get("done_reason") == "length":
        if num_predict > 0 and salida >= num_predict:
            return "limite_salida"
        return "contexto_agotado"
    return None


def _es_error_de_formato(status_code: int, detalle: str) -> bool:
    """¿El error de Ollama se debe a la salida estructurada (`format`)?

    400 que mencionan format/schema/grammar: el esquema no se pudo convertir.
    5xx con mensajes de gramática: el runtime no pudo aplicarla a este modelo.
    En ambos casos se repite la llamada con `format: "json"` genérico.
    """
    d = (detalle or "").lower()
    if status_code == 400:
        return any(p in d for p in ("format", "schema", "grammar"))
    if status_code >= 500:
        return any(p in d for p in ("grammar", "schema", "llama_decode"))
    return False


async def generar(
    prompt: str,
    modelo: str,
    imagenes: list[bytes] | None = None,
    formato_json: bool | dict[str, Any] = True,
    temperatura: float = 0.1,
    num_ctx: int | None = None,
    diagnostico: dict[str, Any] | None = None,
) -> str:
    """
    Llama al modelo y devuelve la respuesta como cadena.

    Si se pasan imágenes, se usa la ruta multimodal. `formato_json` puede ser
    True (JSON genérico) o un esquema JSON: Ollama restringe entonces la
    salida a esa estructura y desaparecen las respuestas con JSON inválido que
    obligaban a repetir la inferencia. Si Ollama no acepta el esquema, se
    repite una vez con JSON genérico. `num_ctx` permite ajustar la ventana al
    tamaño de la petición (nunca por encima de NUM_CTX); si se pasa
    `diagnostico`, se rellena con las métricas de la llamada.
    """
    await verificar_version_ollama()
    await verificar_modelo_local(modelo)

    ventana = min(NUM_CTX, num_ctx) if num_ctx else NUM_CTX
    payload: dict[str, Any] = {
        "model": modelo,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperatura,
            "num_predict": NUM_PREDICT,
            "num_ctx": ventana,
        },
    }

    if isinstance(formato_json, dict):
        payload["format"] = formato_json
    elif formato_json:
        payload["format"] = "json"

    if imagenes:
        payload["images"] = [base64.b64encode(img).decode("ascii") for img in imagenes]

    async with cliente_local(TIMEOUT) as cliente:
        resp = await cliente.post(f"{OLLAMA_URL}/api/generate", json=payload)
        if (
            resp.status_code >= 400
            and isinstance(formato_json, dict)
            and _es_error_de_formato(resp.status_code, getattr(resp, "text", "") or "")
        ):
            logger.warning(
                "Ollama no aceptó el esquema JSON de salida (HTTP %s); se repite con JSON genérico",
                resp.status_code,
            )
            payload["format"] = "json"
            resp = await cliente.post(f"{OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        respuesta = data.get("response")
        if not isinstance(respuesta, str):
            raise RuntimeError("Ollama no devolvió una respuesta textual válida.")
        if diagnostico is not None:
            diagnostico.update(
                num_ctx=ventana,
                num_predict=NUM_PREDICT,
                prompt_eval_count=data.get("prompt_eval_count"),
                eval_count=data.get("eval_count"),
                done_reason=data.get("done_reason"),
                caracteres_prompt=len(prompt),
                imagenes=len(imagenes or []),
            )
            logger.info(
                "Ollama modelo=%s: prompt=%s tok, salida=%s tok, num_ctx=%s, imágenes=%d",
                modelo, data.get("prompt_eval_count"), data.get("eval_count"), ventana,
                len(imagenes or []),
            )
        return respuesta


def _humano_bytes(size: int | None) -> str | None:
    if not isinstance(size, int) or size < 0:
        return None
    valor = float(size)
    for unidad in ("B", "KB", "MB", "GB", "TB"):
        if valor < 1024 or unidad == "TB":
            return f"{valor:.1f} {unidad}" if unidad != "B" else f"{int(valor)} B"
        valor /= 1024
    return str(size)


def _inferir_capacidades(nombre: str, details: dict[str, Any]) -> dict[str, Any]:
    """Inferencia conservadora de capacidades a partir de metadatos Ollama.

    Ollama no declara todavía un campo uniforme de capacidades por modelo en
    /api/tags. Por eso se usan heurísticas explícitas y se marca la salida como
    inferida para que la interfaz pueda advertir al usuario.
    """
    n = nombre.lower()
    families = details.get("families") or []
    if isinstance(families, str):
        families = [families]
    family = str(details.get("family") or "")
    hay_vision = any(str(f).lower() in {"clip", "vision"} for f in families)
    patrones_vision = (
        "llava", "bakllava", "moondream", "minicpm-v", "qwen2-vl",
        "qwen2.5vl", "qwen3-vl", "gemma3", "gemma4", "granite3.2-vision",
        "llama3.2-vision", "mistral-small3.1", "mistral-small3.2",
    )
    if any(p in n for p in patrones_vision):
        hay_vision = True
    return {
        "texto": True,
        "vision": bool(hay_vision),
        "json": True,
        "inferido": True,
        "familia": family or (families[0] if families else None),
    }


def enriquecer_modelo_ollama(modelo: dict[str, Any], modelo_recomendado: str | None = None) -> dict[str, Any]:
    nombre = str(modelo.get("name") or modelo.get("model") or "").strip()
    details = modelo.get("details") if isinstance(modelo.get("details"), dict) else {}
    capacidades = _inferir_capacidades(nombre, details)
    warnings: list[str] = []
    if not capacidades.get("vision"):
        warnings.append("No se ha detectado capacidad de visión. Puede funcionar con texto extraído/OCR, pero no es recomendable para imágenes o PDFs sin texto.")
    if not details:
        warnings.append("Ollama no ha devuelto metadatos técnicos completos para este modelo.")
    recomendado = bool(modelo_recomendado and nombre == modelo_recomendado)
    return {
        "name": nombre,
        "model": modelo.get("model") or nombre,
        "size": modelo.get("size"),
        "size_human": _humano_bytes(modelo.get("size")),
        "modified_at": modelo.get("modified_at"),
        "digest": modelo.get("digest"),
        "family": details.get("family"),
        "families": details.get("families") or [],
        "parameter_size": details.get("parameter_size"),
        "quantization_level": details.get("quantization_level"),
        "format": details.get("format"),
        "capabilities": capacidades,
        "available": True,
        "recommended": recomendado,
        "warnings": warnings,
    }


async def modelos_disponibles(detallado: bool = False) -> list[Any]:
    """Lista los modelos descargados localmente.

    Con detallado=False mantiene compatibilidad y devuelve solo nombres.
    Con detallado=True devuelve metadatos enriquecidos para la interfaz.
    """
    async with cliente_local(TIMEOUT) as cliente:
        resp = await cliente.get(f"{OLLAMA_URL}/api/tags")
        resp.raise_for_status()
        raw_models = [
            m for m in resp.json().get("models", [])
            if isinstance(m, dict)
            and (m.get("name") or m.get("model"))
            and not es_modelo_cloud(str(m.get("name") or m.get("model")))
            and not es_entrada_remota(m)
        ]
    if not detallado:
        return [str(m.get("name") or m.get("model")) for m in raw_models]
    recomendado = os.getenv("MODELO_NOMBRE", "gemma4:e4b")
    return [enriquecer_modelo_ollama(m, recomendado) for m in raw_models]
