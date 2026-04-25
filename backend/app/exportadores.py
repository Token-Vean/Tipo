"""
Exportadores de Tipo v0.1-alpha.

Exporta la propuesta revisada por el usuario. MARCXML e ISBD se generan de
forma determinista a partir de campos descriptivos; no se crean autoridades,
puntos de acceso autorizados ni materias normalizadas.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from datetime import datetime
from typing import Any
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, register_namespace, tostring

from .bibliografico import generar_isbd_desde_campos
from .version import APP_AGENT

MARC_NS = "http://www.loc.gov/MARC21/slim"
register_namespace("", MARC_NS)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _slug(texto: str, max_len: int = 60) -> str:
    if not texto:
        return "sin-titulo"
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^\w\s-]", "", t).strip().lower()
    t = re.sub(r"[\s_]+", "-", t)
    return (t[:max_len] or "sin-titulo").rstrip("-")


def _limpiar_texto(valor: Any) -> str:
    s = "" if valor is None else str(valor)
    return "".join(ch for ch in s if not ((ord(ch) < 32 and ch not in "\n\r\t") or ord(ch) == 127))


def _sanear_csv(valor: Any) -> str:
    texto = _limpiar_texto(valor)
    normalizado_inicio = texto.lstrip(" \ufeff\t\r\n")
    if normalizado_inicio.startswith(("=", "+", "-", "@")) or texto.startswith(("\t", "\r", "\n")):
        return "'" + texto
    return texto


def _campos(payload: dict) -> list[dict]:
    return list(payload.get("propuesta", {}).get("campos", []) or [])


def _valor(campos: list[dict], clave: str) -> Any:
    for c in campos:
        if c.get("clave") == clave:
            return c.get("valor")
    return None


def _txt(valor: Any) -> str:
    if valor in (None, "", []):
        return ""
    if isinstance(valor, list):
        return "; ".join(_limpiar_texto(v).strip() for v in valor if _limpiar_texto(v).strip())
    return _limpiar_texto(valor).strip()


def exportar(formato: str, propuesta: dict) -> tuple[bytes, str, str]:
    if formato == "json":
        return _exportar_json(propuesta)
    if formato == "csv":
        return _exportar_csv(propuesta)
    if formato == "isbd":
        return _exportar_isbd(propuesta)
    if formato == "marcxml":
        return _exportar_marcxml(propuesta)
    raise ValueError(f"Formato no soportado: {formato}")


def _exportar_json(payload: dict) -> tuple[bytes, str, str]:
    limpio = {
        "generado_por": APP_AGENT,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "nota": "Propuesta descriptiva revisable. No contiene puntos de acceso autorizados.",
        "documento": payload.get("documento"),
        "auditoria": payload.get("auditoria"),
        "isbd": payload.get("isbd") or generar_isbd_desde_campos(_campos(payload)),
        "propuesta": payload.get("propuesta"),
    }
    data = json.dumps(limpio, ensure_ascii=False, indent=2).encode("utf-8")
    titulo = _txt(_valor(_campos(payload), "titulo_principal"))
    return data, "application/json; charset=utf-8", f"{_slug(titulo)}-{_timestamp()}.json"


def _exportar_csv(payload: dict) -> tuple[bytes, str, str]:
    salida = io.StringIO(newline="")
    writer = csv.writer(salida, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["id", "clave", "nombre", "valor", "confianza", "evidencia", "estado_evidencia"])
    for c in _campos(payload):
        valor = c.get("valor")
        if isinstance(valor, list):
            valor = " | ".join(str(v) for v in valor)
        writer.writerow([_sanear_csv(c.get("id")), _sanear_csv(c.get("clave")), _sanear_csv(c.get("nombre")), _sanear_csv(valor), _sanear_csv(c.get("confianza")), _sanear_csv(c.get("evidencia")), _sanear_csv(c.get("estado_evidencia"))])
    data = ("\ufeff" + salida.getvalue()).encode("utf-8")
    titulo = _txt(_valor(_campos(payload), "titulo_principal"))
    return data, "text/csv; charset=utf-8", f"{_slug(titulo)}-{_timestamp()}.csv"


def _exportar_isbd(payload: dict) -> tuple[bytes, str, str]:
    isbd = payload.get("isbd") or generar_isbd_desde_campos(_campos(payload))
    cabecera = "Tipo — ISBD derivado\nResultado revisable. No incluye puntos de acceso autorizados ni materias normalizadas.\n\n"
    data = (cabecera + isbd + "\n").encode("utf-8")
    titulo = _txt(_valor(_campos(payload), "titulo_principal"))
    return data, "text/plain; charset=utf-8", f"{_slug(titulo)}-isbd-{_timestamp()}.txt"


def _sf(parent: Element, code: str, valor: Any) -> None:
    texto = _txt(valor)
    if texto:
        SubElement(parent, f"{{{MARC_NS}}}subfield", {"code": code}).text = texto


def _datafield(record: Element, tag: str, ind1: str = " ", ind2: str = " ") -> Element:
    return SubElement(record, f"{{{MARC_NS}}}datafield", {"tag": tag, "ind1": ind1, "ind2": ind2})


def _pretty_xml(elemento: Element) -> bytes:
    crudo = tostring(elemento, encoding="utf-8")
    pretty = minidom.parseString(crudo).toprettyxml(indent="  ", encoding="utf-8")
    return b"\n".join(linea for linea in pretty.split(b"\n") if linea.strip())


def _calcular_245_ind2(titulo: str) -> str:
    s = (titulo or "").strip().lower()
    for art in ["el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas ", "the ", "a ", "an "]:
        if s.startswith(art):
            return str(min(9, len(art)))
    return "0"


def _exportar_marcxml(payload: dict) -> tuple[bytes, str, str]:
    campos = _campos(payload)
    record = Element(f"{{{MARC_NS}}}record")
    SubElement(record, f"{{{MARC_NS}}}leader").text = "00000nam a2200000 i 4500"
    SubElement(record, f"{{{MARC_NS}}}controlfield", {"tag": "005"}).text = datetime.utcnow().strftime("%Y%m%d%H%M%S.0")
    isbn = _valor(campos, "isbn")
    if isbn:
        f020 = _datafield(record, "020")
        _sf(f020, "a", isbn)
    f040 = _datafield(record, "040")
    _sf(f040, "a", "Tipo-local")
    _sf(f040, "b", "spa")
    _sf(f040, "e", "rda")
    titulo = _txt(_valor(campos, "titulo_principal"))
    if titulo:
        f245 = _datafield(record, "245", "0", _calcular_245_ind2(titulo))
        _sf(f245, "a", titulo)
        _sf(f245, "b", _valor(campos, "subtitulo"))
        _sf(f245, "c", _valor(campos, "mencion_responsabilidad"))
    if _valor(campos, "mencion_edicion"):
        f250 = _datafield(record, "250")
        _sf(f250, "a", _valor(campos, "mencion_edicion"))
    if any(_valor(campos, k) for k in ("lugar_publicacion", "editor", "fecha_publicacion")):
        f264 = _datafield(record, "264", " ", "1")
        _sf(f264, "a", _valor(campos, "lugar_publicacion"))
        _sf(f264, "b", _valor(campos, "editor"))
        _sf(f264, "c", _valor(campos, "fecha_publicacion"))
    if any(_valor(campos, k) for k in ("extension", "ilustraciones", "dimensiones")):
        f300 = _datafield(record, "300")
        _sf(f300, "a", _valor(campos, "extension"))
        _sf(f300, "b", _valor(campos, "ilustraciones"))
        _sf(f300, "c", _valor(campos, "dimensiones"))
    for tag, clave in (("336", "tipo_contenido"), ("337", "tipo_medio"), ("338", "tipo_soporte")):
        if _valor(campos, clave):
            f = _datafield(record, tag)
            _sf(f, "a", _valor(campos, clave))
    if _valor(campos, "serie_transcrita"):
        f490 = _datafield(record, "490", "0", " ")
        _sf(f490, "a", _valor(campos, "serie_transcrita"))
    for tag, clave in (("500", "nota_general"), ("504", "nota_bibliografia"), ("520", "resumen"), ("546", "nota_lengua")):
        if _valor(campos, clave):
            f = _datafield(record, tag)
            _sf(f, "a", _valor(campos, clave))
    titulo_archivo = titulo or "registro-tipo"
    return _pretty_xml(record), "application/marcxml+xml; charset=utf-8", f"{_slug(titulo_archivo)}-{_timestamp()}.xml"
