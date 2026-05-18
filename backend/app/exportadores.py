"""
Exportadores de Tipo v0.3.0-beta.1.

Exporta la propuesta revisada por el usuario. MARCXML e ISBD se generan de
forma determinista a partir de campos descriptivos; no se crean autoridades,
puntos de acceso autorizados ni materias normalizadas.

v0.3.0-beta.1 — Calidad para importación en SIGB:
    - 008 (control field, longitud fija 40) emitido siempre, con fecha de
      catalogación, fecha 1 derivada del año detectado en fecha_publicacion,
      código de país inferido por idioma de catalogación e idioma del recurso.
    - 041 emitido siempre. Si el esquema entrega lengua_texto se respeta; si
      no, se emite el idioma de salida normalizado a código MARC de 3 letras.
    - 245 con ind1=1 por defecto para que los SIGB generen entrada secundaria
      automática por título (Tipo no produce 1xx).
    - Subcampos $b/$c del 245 y $a del 490 limpios de puntuación ISBD inicial
      (':', '/', ';', '='): la puntuación de visualización la añade el SIGB.
    - 250 normalizada a forma abreviada RDA ('1ª Edición' → '1ª ed.', etc.)
      cuando el patrón es claro; en casos complejos se preserva el original.
    - 264 con ind1=1 (publicación vigente) para mayor precisión semántica.
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


# ---------------------------------------------------------------------------
# Helpers de normalización MARC21 (v0.3.0-beta).
#
# Estos helpers elevan la calidad del registro generado a "importable en SIGB
# con revisión mínima". Hasta v0.2.0-beta.7 los registros eran propuestas
# revisables que carecían de algunos campos que la mayoría de los sistemas
# bibliotecarios consideran obligatorios (008, 041) y arrastraban detalles
# que generaban errores de carga (puntuación ISBD dentro de los subcampos,
# ind1 del 245 igual a 0 cuando no hay 1xx, formas no estandarizadas de la
# mención de edición). Todo lo que sigue es determinista, sin recurrir al LLM.
# ---------------------------------------------------------------------------

# Mapa ISO 639-1 → MARC Language Code (subset suficiente para el alcance de
# Tipo: monografía impresa moderna). Se amplía cuando se añadan más idiomas.
_MAP_IDIOMA_MARC = {
    "es": "spa", "spa": "spa",
    "en": "eng", "eng": "eng",
    "fr": "fre", "fre": "fre",
    "pt": "por", "por": "por",
    "it": "ita", "ita": "ita",
    "de": "ger", "ger": "ger",
    "ca": "cat", "cat": "cat",
    "eu": "baq", "baq": "baq",
    "gl": "glg", "glg": "glg",
}

# Mapa de idiomas dominantes a códigos MARC de país. Heurística determinista:
# el idioma del texto descriptivo apunta al país más probable de la edición
# para que el 008/15-17 no quede vacío. Si en el futuro el esquema permite
# país explícito se sustituye por ese valor.
_PAIS_POR_IDIOMA = {
    "spa": "sp ", "cat": "sp ", "baq": "sp ", "glg": "sp ",
    "eng": "enk",   # Reino Unido como conservador; "xxu" para EE.UU. también vale
    "fre": "fr ", "ger": "gw ", "ita": "it ", "por": "po ",
}


def _idioma_marc(idioma_salida: str | None) -> str:
    """Devuelve el código MARC de 3 letras. Por defecto 'spa'."""
    if not idioma_salida:
        return "spa"
    return _MAP_IDIOMA_MARC.get(idioma_salida.strip().lower(), "spa")


def _pais_marc(idioma_marc: str) -> str:
    """Devuelve el código MARC21 de país (3 chars, rellenado con espacios)."""
    return _PAIS_POR_IDIOMA.get(idioma_marc, "xx ")


_RE_ANIO = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")


def _extraer_anio(valor: Any) -> str:
    """Extrae el primer año de 4 cifras presente en una cadena (1500-2099).
    Devuelve cadena vacía si no encuentra ninguno. No inventa fechas."""
    m = _RE_ANIO.search(_txt(valor) or "")
    return m.group(1) if m else ""


def _construir_008(campos: list[dict], idioma_marc: str) -> str:
    """Construye un 008 determinístico mínimo, suficiente para importación.

    Posiciones según LC MARC21 (libros):
      00-05  Fecha de catalogación AAMMDD (hoy)
      06     Tipo de fecha. 's' (single) si hay año detectado; 'n' (unknown)
             si no se ha podido determinar
      07-10  Fecha 1 (publicación) o 'uuuu'
      11-14  Fecha 2: 4 espacios para 's' o 'n'
      15-17  Código de país de publicación
      18-22  Ilustraciones (5 caracteres). Dejamos blancos: la inferencia
             determinista a partir de '$b' del 300 es frágil.
      23     Forma del ítem: '#' (texto impreso convencional)
      24-27  Naturaleza del contenido: blancos
      28     Publicación gubernamental: '#'
      29     Actas de congreso: '0'
      30     Festschrift: '0'
      31     Índice: '0'
      32     Indefinido
      33     Forma literaria: '0' (no ficción) por defecto (mantiene la
             cautela: Tipo no clasifica; el catalogador lo afina)
      34     Biografía: '#'
      35-37  Idioma (3 caracteres, código MARC)
      38     Registro modificado: '#'
      39     Fuente de catalogación: 'd' (otra)

    Longitud final: 40 caracteres exactos.
    """
    hoy = datetime.utcnow().strftime("%y%m%d")        # 00-05
    anio = _extraer_anio(_valor(campos, "fecha_publicacion"))
    if anio:
        tipo_fecha = "s"
        fecha1 = anio
    else:
        tipo_fecha = "n"
        fecha1 = "uuuu"
    fecha2 = "    "
    pais = _pais_marc(idioma_marc)
    pos18_22 = "    |"  # ilustraciones desconocidas + final reservado
    pos23 = " "
    pos24_27 = "    "
    pos28 = " "
    pos29_33 = "0000 "   # congreso, festschrift, índice, indef., forma literaria
    pos34 = " "          # biografía
    pos38 = " "          # modificación
    pos39 = "d"          # fuente de catalogación
    valor = (
        hoy + tipo_fecha + fecha1 + fecha2 + pais
        + pos18_22 + pos23 + pos24_27 + pos28 + pos29_33 + pos34
        + idioma_marc + pos38 + pos39
    )
    # Garantizar exactamente 40 caracteres por si alguna ampliación futura
    # se desfasa. Truncamos o rellenamos con espacios sin perder posiciones.
    if len(valor) < 40:
        valor = valor.ljust(40)
    elif len(valor) > 40:
        valor = valor[:40]
    return valor


# Puntuación ISBD que no debe ir DENTRO de los subcampos MARC. La unidad
# productora del SIGB añade la puntuación de visualización a partir de los
# delimitadores de subcampo. Si entra como contenido, se duplica al volver
# a renderizar y los catálogos quedan feos.
_PUNTUACION_ISBD_INICIAL = (
    " : ", " :", ": ", ":",
    " / ", " /", "/ ", "/",
    " ; ", " ;", "; ", ";",
    " = ", " =", "= ", "=",
    " — ", " --", "-- ", " - ",
    ", ", ",",
)


def _limpiar_puntuacion_inicial(valor: Any) -> str:
    """Elimina la puntuación ISBD que algunos campos arrastran al inicio
    (':', '/', ';', '=', ', ', ...). Es seguro porque se aplica solo al inicio
    del subcampo, donde nunca debería haber signos de puntuación literales
    del título o de la mención. Si tras la limpieza queda cadena vacía, se
    devuelve también vacía (no introduce espacios espurios)."""
    s = _txt(valor)
    if not s:
        return ""
    cambiado = True
    while cambiado:
        cambiado = False
        for sufijo in _PUNTUACION_ISBD_INICIAL:
            if s.startswith(sufijo):
                s = s[len(sufijo):]
                cambiado = True
                break
        s = s.lstrip()
    return s


_RE_EDICION_ORDINAL_LARGA = re.compile(
    r"^\s*(\d+)\s*(º|ª|ra|da|ta|na|nd|st|rd|th)?\s*(edición|ediciones|edition|edn\.?)\s*$",
    re.IGNORECASE,
)


def _normalizar_edicion(valor: Any) -> str:
    """Normaliza la mención de edición a forma abreviada RDA cuando el patrón
    es claro y conservador. 'Primera Edición' o '1ª Edición' → '1ª ed.'.
    Si el texto es algo más complejo (revisada, ampliada, bilingüe, etc.) se
    devuelve tal cual. La función nunca inventa información; solo abrevia
    'Edición' o 'Edition' cuando es el único término."""
    s = _txt(valor)
    if not s:
        return s
    m = _RE_EDICION_ORDINAL_LARGA.match(s)
    if m:
        numero = m.group(1)
        return f"{numero}ª ed."
    # Mapas de "Primera"…"Décima" a número
    mapa_ord = {
        "primera": "1", "segunda": "2", "tercera": "3", "cuarta": "4",
        "quinta": "5", "sexta": "6", "séptima": "7", "octava": "8",
        "novena": "9", "décima": "10",
        "first": "1", "second": "2", "third": "3", "fourth": "4",
    }
    m2 = re.match(r"^\s*(\w+)\s*(edición|edition)\s*$", s, re.IGNORECASE)
    if m2:
        num = mapa_ord.get(m2.group(1).lower())
        if num:
            return f"{num}ª ed."
    return s


def _construir_record_marcxml(
    campos: list[dict],
    idioma_salida: str | None = None,
) -> Element:
    """Construye un <record> MARCXML completo a partir de los campos atómicos
    de la propuesta. Fuente única de verdad: la usa tanto la exportación de
    un libro como la de colección (lote).

    Implementa todas las normalizaciones de calidad para importación SIGB:
    leader + 005, 008 determinístico, 041 con código MARC del idioma, 040
    con marca local, 245 con ind1=1 (entrada automática por título cuando no
    hay 1xx), subcampos del 245 limpios de puntuación ISBD inicial, 250 en
    forma abreviada RDA, 264 ind1=1 (publicación vigente), 300, 336/337/338,
    490, 500/504/520/546.
    """
    idioma_marc = _idioma_marc(idioma_salida)
    record = Element(f"{{{MARC_NS}}}record")
    SubElement(record, f"{{{MARC_NS}}}leader").text = "00000nam a2200000 i 4500"
    SubElement(record, f"{{{MARC_NS}}}controlfield", {"tag": "005"}).text = (
        datetime.utcnow().strftime("%Y%m%d%H%M%S.0")
    )
    SubElement(record, f"{{{MARC_NS}}}controlfield", {"tag": "008"}).text = (
        _construir_008(campos, idioma_marc)
    )

    isbn = _valor(campos, "isbn")
    if isbn:
        f020 = _datafield(record, "020")
        _sf(f020, "a", isbn)

    # 040: marca local. Se mantiene 'Tipo-local' como agencia productora.
    # 'b' = idioma de catalogación; 'e' = reglas de descripción (RDA).
    f040 = _datafield(record, "040")
    _sf(f040, "a", "Tipo-local")
    _sf(f040, "b", idioma_marc)
    _sf(f040, "e", "rda")

    # 041: idioma del recurso. Aunque 008/35-37 ya lleva el código, muchos
    # SIGB indexan facets a partir de 041, así que lo emitimos siempre.
    f041 = _datafield(record, "041", "0", " ")
    _sf(f041, "a", idioma_marc)

    titulo = _txt(_valor(campos, "titulo_principal"))
    if titulo:
        # ind1 = 1: el catálogo genera entrada secundaria por título.
        # Tipo no produce 1xx, así que esta opción asegura que el libro
        # siga siendo buscable por título tras la importación.
        f245 = _datafield(record, "245", "1", _calcular_245_ind2(titulo))
        _sf(f245, "a", _limpiar_puntuacion_inicial(titulo))
        _sf(f245, "b", _limpiar_puntuacion_inicial(_valor(campos, "subtitulo")))
        _sf(f245, "c", _limpiar_puntuacion_inicial(_valor(campos, "mencion_responsabilidad")))

    edicion = _valor(campos, "mencion_edicion")
    if edicion:
        f250 = _datafield(record, "250")
        _sf(f250, "a", _normalizar_edicion(edicion))

    if any(_valor(campos, k) for k in ("lugar_publicacion", "editor", "fecha_publicacion")):
        # ind1 = 1: publicación vigente (en oposición a anterior o posterior).
        # ind2 = 1: función "publication" (vs distribución, fabricación, etc.).
        f264 = _datafield(record, "264", "1", "1")
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
        _sf(f490, "a", _limpiar_puntuacion_inicial(_valor(campos, "serie_transcrita")))

    for tag, clave in (("500", "nota_general"), ("504", "nota_bibliografia"),
                       ("520", "resumen"), ("546", "nota_lengua")):
        if _valor(campos, clave):
            f = _datafield(record, tag)
            _sf(f, "a", _valor(campos, clave))

    return record


def _exportar_marcxml(payload: dict) -> tuple[bytes, str, str]:
    campos = _campos(payload)
    idioma_salida = payload.get("idioma_salida") if isinstance(payload, dict) else None
    record = _construir_record_marcxml(campos, idioma_salida)
    titulo_archivo = _txt(_valor(campos, "titulo_principal")) or "registro-tipo"
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


def generar_marc21_texto(campos: list[dict], idioma_salida: str | None = None) -> list[dict]:
    """Devuelve una lista de líneas MARC21 estructuradas, con etiqueta,
    indicadores y subcampos en texto plano. Cada elemento del listado es:
        {"tag": "245", "ind1": "1", "ind2": "0", "texto": "245 1 0 $a Título / $c Autor"}
    Apto tanto para renderizar en pantalla como para volcar a TXT.

    Aplica las mismas normalizaciones MARC21 que _construir_record_marcxml
    para que la pestaña MARC21 de la UI y el TXT exportado coincidan con el
    MARCXML que se descargará.
    """
    lineas: list[dict] = []
    idioma_marc = _idioma_marc(idioma_salida)

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

    # 008 — códigos de control, longitud fija 40 caracteres.
    lineas.append({
        "tag": "008",
        "ind1": "",
        "ind2": "",
        "texto": f"008     {_construir_008(campos, idioma_marc)}",
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
    add("040", " ", " ", [_subcampo("a", "Tipo-local"), _subcampo("b", idioma_marc), _subcampo("e", "rda")])

    # 041 — lengua del recurso (siempre presente; índice estable de facets)
    leng = _valor(campos, "lengua_texto") or idioma_marc
    idi_orig = _valor(campos, "idioma_original")
    partes041 = [_subcampo("a", leng)]
    if idi_orig:
        partes041.append(_subcampo("h", idi_orig))
    add("041", "1" if idi_orig else "0", " ", partes041)

    # 240 — título uniforme (título original)
    tit_orig = _valor(campos, "titulo_original")
    if tit_orig:
        add("240", "1", "0", [_subcampo("a", tit_orig)])

    # 245 — título y mención de responsabilidad.
    # ind1=1 fuerza que el SIGB genere entrada secundaria por título, lo que
    # mantiene los registros buscables aunque Tipo no produzca 1xx.
    titulo = _txt(_valor(campos, "titulo_principal"))
    if titulo:
        partes = [
            _subcampo("a", _limpiar_puntuacion_inicial(titulo)),
            _subcampo("b", _limpiar_puntuacion_inicial(_valor(campos, "subtitulo"))),
            _subcampo("c", _limpiar_puntuacion_inicial(_valor(campos, "mencion_responsabilidad"))),
        ]
        add("245", "1", _calcular_245_ind2(titulo), partes)

    # 250 — edición, normalizada a forma abreviada RDA cuando se puede.
    edicion = _valor(campos, "mencion_edicion")
    if edicion:
        add("250", " ", " ", [_subcampo("a", _normalizar_edicion(edicion))])

    # 264 1 1 — publicación vigente
    if any(_valor(campos, k) for k in ("lugar_publicacion", "editor", "fecha_publicacion")):
        add("264", "1", "1", [
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
        add("490", "0", " ", [_subcampo("a", _limpiar_puntuacion_inicial(_valor(campos, "serie_transcrita")))])

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
