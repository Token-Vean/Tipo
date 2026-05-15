"""
Exportadores de Tipo v0.2.0-beta.6.

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
    if formato == "marc-txt":
        return _exportar_marc_txt(propuesta)
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


# ---------------------------------------------------------------------------
# Representación MARC21 en texto plano (etiquetada, monoespaciada).
# Pensada para visualización en pantalla y copia directa al portapapeles
# para pegar en un OPAC. Refleja exactamente lo que escribe _exportar_marcxml.
# ---------------------------------------------------------------------------

def _ind(v: str) -> str:
    """Indicador en formato visible: espacio → '#', dígito tal cual."""
    if v == " " or v == "" or v is None:
        return "#"
    return str(v)[:1]


def _subcampo(code: str, valor: Any) -> str:
    texto = _txt(valor)
    return f" ${code} {texto}" if texto else ""


def _subcampos_lista(code: str, valor: Any) -> list[str]:
    """Una lista de valores → varios subcampos $code repetidos."""
    if valor in (None, "", []):
        return []
    items = valor if isinstance(valor, list) else [valor]
    return [f" ${code} {_limpiar_texto(v).strip()}" for v in items if _limpiar_texto(v).strip()]


def generar_marc21_texto(campos: list[dict]) -> list[dict]:
    """Devuelve una lista de líneas MARC21 estructuradas, con etiqueta,
    indicadores y subcampos en texto plano. Cada elemento del listado es:
        {"tag": "245", "ind1": "0", "ind2": "0", "texto": "245 0 0 $a Título / $c Autor"}
    Apto tanto para renderizar en pantalla como para volcar a TXT.
    """
    lineas: list[dict] = []

    def add(tag: str, ind1: str, ind2: str, partes: list[str]) -> None:
        if not any(p.strip() for p in partes):
            return
        cuerpo = "".join(partes).strip()
        lineas.append({
            "tag": tag,
            "ind1": _ind(ind1),
            "ind2": _ind(ind2),
            "texto": f"{tag} {_ind(ind1)} {_ind(ind2)} {cuerpo}",
        })

    # 005 — fecha y hora de la última transacción
    lineas.append({
        "tag": "005",
        "ind1": "",
        "ind2": "",
        "texto": f"005     {datetime.utcnow().strftime('%Y%m%d%H%M%S.0')}",
    })

    # 017 — depósito legal
    dl = _valor(campos, "deposito_legal")
    if dl:
        add("017", " ", " ", [_subcampo("a", dl)])

    # 020 — ISBN (puede ser lista)
    isbn = _valor(campos, "isbn")
    if isbn:
        for sub in _subcampos_lista("a", isbn):
            add("020", " ", " ", [sub])

    # 040 — fuente de catalogación
    add("040", " ", " ", [_subcampo("a", "Tipo-local"), _subcampo("b", "spa"), _subcampo("e", "rda")])

    # 041 — lengua, con $h para idioma original si lo hay
    leng = _valor(campos, "lengua_texto")
    idi_orig = _valor(campos, "idioma_original")
    if leng or idi_orig:
        partes = [_subcampo("a", leng)]
        if idi_orig:
            partes.append(_subcampo("h", idi_orig))
        add("041", "1" if idi_orig else "0", " ", partes)

    # 240 — título uniforme (título original)
    tit_orig = _valor(campos, "titulo_original")
    if tit_orig:
        add("240", "1", "0", [_subcampo("a", tit_orig)])

    # 245 — título y mención de responsabilidad
    titulo = _txt(_valor(campos, "titulo_principal"))
    if titulo:
        partes = [
            _subcampo("a", titulo),
            _subcampo("b", _valor(campos, "subtitulo")),
            _subcampo("c", _valor(campos, "mencion_responsabilidad")),
        ]
        add("245", "0", _calcular_245_ind2(titulo), partes)

    # 250 — edición
    if _valor(campos, "mencion_edicion"):
        add("250", " ", " ", [_subcampo("a", _valor(campos, "mencion_edicion"))])

    # 264 _1 — publicación
    if any(_valor(campos, k) for k in ("lugar_publicacion", "editor", "fecha_publicacion")):
        add("264", " ", "1", [
            _subcampo("a", _valor(campos, "lugar_publicacion")),
            _subcampo("b", _valor(campos, "editor")),
            _subcampo("c", _valor(campos, "fecha_publicacion")),
        ])

    # 300 — descripción física
    if any(_valor(campos, k) for k in ("extension", "ilustraciones", "dimensiones")):
        add("300", " ", " ", [
            _subcampo("a", _valor(campos, "extension")),
            _subcampo("b", _valor(campos, "ilustraciones")),
            _subcampo("c", _valor(campos, "dimensiones")),
        ])

    # 336/337/338 — tipo contenido/medio/soporte
    for tag, clave in (("336", "tipo_contenido"), ("337", "tipo_medio"), ("338", "tipo_soporte")):
        if _valor(campos, clave):
            add(tag, " ", " ", [_subcampo("a", _valor(campos, clave))])

    # 490 0 — serie transcrita
    if _valor(campos, "serie_transcrita"):
        add("490", "0", " ", [_subcampo("a", _valor(campos, "serie_transcrita"))])

    # 500/504/520/546 — notas
    for tag, clave in (("500", "nota_general"), ("504", "nota_bibliografia"),
                       ("520", "resumen"), ("546", "nota_lengua")):
        if _valor(campos, clave):
            add(tag, " ", " ", [_subcampo("a", _valor(campos, clave))])

    return lineas


def marc21_a_texto_plano(lineas: list[dict]) -> str:
    """Convierte la lista estructurada de generar_marc21_texto en un bloque
    de texto plano monoespaciado, listo para copiar y pegar."""
    return "\n".join(l["texto"] for l in lineas)


def _exportar_marc_txt(payload: dict) -> tuple[bytes, str, str]:
    campos = _campos(payload)
    lineas = generar_marc21_texto(campos)
    cabecera = (
        "Tipo — MARC21 en texto plano\n"
        "Propuesta revisable. No incluye puntos de acceso autorizados ni materias.\n"
        "Indicador en blanco se muestra como '#'.\n\n"
    )
    data = (cabecera + marc21_a_texto_plano(lineas) + "\n").encode("utf-8")
    titulo = _txt(_valor(campos, "titulo_principal"))
    return data, "text/plain; charset=utf-8", f"{_slug(titulo)}-marc21-{_timestamp()}.txt"
