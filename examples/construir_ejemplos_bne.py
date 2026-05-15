#!/usr/bin/env python3
"""
construir_ejemplos_bne.py — Generador de ejemplos few-shot para Tipo
===========================================================================

Para qué sirve
--------------
Tipo mejora su precisión cuando el prompt incluye unos pocos ejemplos
resueltos ("few-shot"): casos en los que se ve cómo distinguir autor de
traductor, título de título original, o cuándo devolver null. Este script
construye ese fichero de ejemplos (schemas/ejemplos-monografia.yaml) a partir
de registros bibliográficos reales de la BNE.

Cómo se integra "internamente" en la herramienta
-------------------------------------------------
Este es un script de TIEMPO DE CONSTRUCCIÓN, no de tiempo de ejecución. La
idea es:

    1. El desarrollador descarga unos pocos registros MARCXML de la BNE
       (a mano desde el catálogo, o desde datos.bne.es / el portal de la
       Bibliografía Española en Línea). Bastan entre 3 y 8 registros bien
       elegidos: una traducción, una obra con varios responsables, una obra
       sin ISBN, una reedición, etc.
    2. Ejecuta este script UNA VEZ sobre esos ficheros.
    3. El script produce schemas/ejemplos-monografia.yaml.
    4. Ese YAML se copia dentro de la imagen de Tipo, en /app/schemas/, junto
       al esquema. Viaja empaquetado con la herramienta.

En producción Tipo NO descarga nada: lee el YAML del disco. Esto es coherente
con su diseño local-first y sin dependencia de red. La BNE solo interviene en
la fase de preparación, en la máquina del desarrollador.

Por qué a partir de MARCXML y no "scrapeando"
---------------------------------------------
Un registro MARCXML ya tiene los datos descriptivos identificados por campo y
subcampo. Eso permite construir un ejemplo FIEL: sabemos qué es el título
(245$a), qué es la mención de responsabilidad literal (245$c), qué es el
título original (240$a), el depósito legal (017$a), etc. El script "rehidrata"
con esos datos un bloque de texto que imita lo que Tipo vería en las zonas de
un libro, y empareja ese texto con la salida JSON correcta.

Los ejemplos resultantes son material de entrenamiento del prompt, no copias
de catálogo: se reordenan y se presentan como portada/verso simulados.

Uso
---
    # A partir de ficheros MARCXML ya descargados (modo recomendado, offline):
    python construir_ejemplos_bne.py registros/*.xml -o ../schemas/ejemplos-monografia.yaml

    # Inspeccionar qué se extraería, sin escribir:
    python construir_ejemplos_bne.py registros/*.xml --dry-run

    # Opcionalmente, descargar por SRU desde la BNE (requiere red; revisar los
    # ejemplos a mano antes de empaquetarlos):
    python construir_ejemplos_bne.py --sru "bib.materia=arquitectura" --sru-max 5 -o salida.yaml

Dependencias: solo la librería estándar y PyYAML (ya en requirements de Tipo).
La descarga SRU usa urllib; si no hay red, simplemente no se usa esa opción.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Falta PyYAML. Instálalo con: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


MARC_NS = {"marc": "http://www.loc.gov/MARC21/slim"}

# SRU de la BNE. Solo se usa con --sru; en el flujo normal no se toca la red.
BNE_SRU_URL = "http://catalogo.bne.es/sru"


# ---------------------------------------------------------------------------
# Lectura de MARCXML
# ---------------------------------------------------------------------------

def _texto_subcampo(campo: ET.Element, codigo: str) -> str | None:
    """Devuelve el texto del primer subcampo con el código dado."""
    for sub in campo.findall("marc:subfield", MARC_NS):
        if sub.get("code") == codigo:
            return (sub.text or "").strip() or None
    return None


def _subcampos_unidos(campo: ET.Element, codigos: str, sep: str = " ") -> str | None:
    """Une, en orden de aparición, los subcampos cuyos códigos estén en `codigos`."""
    partes: list[str] = []
    for sub in campo.findall("marc:subfield", MARC_NS):
        if sub.get("code") in codigos:
            t = (sub.text or "").strip()
            if t:
                partes.append(t)
    return sep.join(partes) or None


def _campos(record: ET.Element, tag: str) -> list[ET.Element]:
    return [
        c for c in record.findall("marc:datafield", MARC_NS)
        if c.get("tag") == tag
    ]


def _primer_campo(record: ET.Element, tag: str) -> ET.Element | None:
    campos = _campos(record, tag)
    return campos[0] if campos else None


def _limpiar_isbd(valor: str | None) -> str | None:
    """Quita puntuación ISBD final típica (/, :, ;, ,, .) para un valor atómico."""
    if not valor:
        return None
    return valor.rstrip(" /:;,.").strip() or None


def extraer_datos_registro(record: ET.Element) -> dict:
    """
    Extrae de un <record> MARCXML los datos que Tipo intenta proponer.
    Devuelve un dict con las claves del esquema de Tipo.
    """
    datos: dict = {}

    # 020 $a ISBN (puede haber varios)
    isbns: list[str] = []
    for c in _campos(record, "020"):
        isbn = _texto_subcampo(c, "a")
        if isbn:
            # El subcampo suele traer "(rústica)" u otra coletilla: nos quedamos
            # con el primer token, que es el número.
            isbns.append(isbn.split()[0].strip())
    if isbns:
        datos["isbn"] = isbns

    # 017 $a Depósito legal
    c017 = _primer_campo(record, "017")
    if c017 is not None:
        datos["deposito_legal"] = _texto_subcampo(c017, "a")

    # 041 $a lengua del texto / $h lengua original
    c041 = _primer_campo(record, "041")
    if c041 is not None:
        datos["_041a"] = _texto_subcampo(c041, "a")
        datos["_041h"] = _texto_subcampo(c041, "h")

    # 245 $a título, $b subtítulo, $c mención de responsabilidad
    c245 = _primer_campo(record, "245")
    if c245 is not None:
        datos["titulo_principal"] = _limpiar_isbd(_texto_subcampo(c245, "a"))
        datos["subtitulo"] = _limpiar_isbd(_texto_subcampo(c245, "b"))
        datos["mencion_responsabilidad"] = _limpiar_isbd(_texto_subcampo(c245, "c"))

    # 240 $a título original / uniforme
    c240 = _primer_campo(record, "240")
    if c240 is not None:
        datos["titulo_original"] = _limpiar_isbd(_texto_subcampo(c240, "a"))

    # 250 $a mención de edición
    c250 = _primer_campo(record, "250")
    if c250 is not None:
        datos["mencion_edicion"] = _limpiar_isbd(_texto_subcampo(c250, "a"))

    # 264 publicación: $a lugar, $b editor, $c fecha
    lugar = editor = fecha = None
    for c in _campos(record, "264"):
        ind2 = c.get("ind2")
        if ind2 == "1" or (lugar is None and editor is None):
            lugar = lugar or _limpiar_isbd(_texto_subcampo(c, "a"))
            editor = editor or _limpiar_isbd(_texto_subcampo(c, "b"))
            fecha = fecha or _limpiar_isbd(_texto_subcampo(c, "c"))
    # Compatibilidad con registros antiguos en 260
    if lugar is None and editor is None:
        c260 = _primer_campo(record, "260")
        if c260 is not None:
            lugar = _limpiar_isbd(_texto_subcampo(c260, "a"))
            editor = _limpiar_isbd(_texto_subcampo(c260, "b"))
            fecha = _limpiar_isbd(_texto_subcampo(c260, "c"))
    datos["lugar_publicacion"] = lugar
    datos["editor"] = editor
    if fecha:
        # Dejar solo el año si es posible.
        import re
        m = re.search(r"\d{4}", fecha)
        datos["fecha_publicacion"] = m.group(0) if m else fecha

    # 490 $a serie transcrita
    c490 = _primer_campo(record, "490")
    if c490 is not None:
        datos["serie_transcrita"] = _subcampos_unidos(c490, "av", ", ")

    # 546 $a nota de lengua
    c546 = _primer_campo(record, "546")
    if c546 is not None:
        datos["nota_lengua"] = _texto_subcampo(c546, "a")

    # 500 $a nota general (solo la primera, como ejemplo)
    c500 = _primer_campo(record, "500")
    if c500 is not None:
        datos["nota_general"] = _texto_subcampo(c500, "a")

    return {k: v for k, v in datos.items() if v not in (None, "", [])}


# ---------------------------------------------------------------------------
# Construcción del ejemplo (texto simulado + salida JSON)
# ---------------------------------------------------------------------------

# Códigos de lengua MARC más habituales en la BNE -> nombre en español.
_LENGUAS = {
    "spa": "español", "eng": "inglés", "fre": "francés", "fra": "francés",
    "ger": "alemán", "deu": "alemán", "ita": "italiano", "por": "portugués",
    "cat": "catalán", "glg": "gallego", "eus": "euskera", "baq": "euskera",
    "lat": "latín", "grc": "griego antiguo", "rus": "ruso", "jpn": "japonés",
}


def _nombre_lengua(codigo: str | None) -> str | None:
    if not codigo:
        return None
    return _LENGUAS.get(codigo.strip().lower())


def construir_texto_simulado(datos: dict) -> str:
    """
    "Rehidrata" un bloque de texto que imita lo que Tipo vería en las zonas
    preliminares de un libro, usando las cabeceras de zona reales.
    """
    portada: list[str] = []
    if datos.get("titulo_principal"):
        portada.append(datos["titulo_principal"].upper())
    if datos.get("subtitulo"):
        portada.append(datos["subtitulo"])
    if datos.get("mencion_responsabilidad"):
        portada.append(datos["mencion_responsabilidad"])
    if datos.get("mencion_edicion"):
        portada.append(datos["mencion_edicion"])
    pie = " : ".join(x for x in (datos.get("lugar_publicacion"), datos.get("editor")) if x)
    if pie and datos.get("fecha_publicacion"):
        pie = f"{pie}, {datos['fecha_publicacion']}"
    if pie:
        portada.append(pie)

    verso: list[str] = []
    if datos.get("titulo_original"):
        verso.append(f"Título original: {datos['titulo_original']}")
    if datos.get("fecha_publicacion"):
        verso.append(f"© {datos['fecha_publicacion']}, {datos.get('editor') or 'el editor'}")
    if datos.get("isbn"):
        for isbn in datos["isbn"]:
            verso.append(f"ISBN: {isbn}")
    if datos.get("deposito_legal"):
        verso.append(f"Depósito legal: {datos['deposito_legal']}")
    if datos.get("serie_transcrita"):
        verso.append(datos["serie_transcrita"])

    bloques = [
        "########## ZONA: PRELIMINARES (cubierta, portada, verso de portada, índice) ##########",
        "",
        "===== preliminares · página 3 de 200 =====",
        "\n".join(portada),
    ]
    if verso:
        bloques += [
            "",
            "===== preliminares · página 4 de 200 =====",
            "\n".join(verso),
        ]
    return "\n".join(bloques)


def construir_salida(datos: dict, claves_esquema: list[str]) -> dict:
    """
    Construye el objeto JSON de salida esperado. Para cada clave del esquema:
    si hay dato, lo pone con confianza alta y una evidencia plausible; si no,
    lo deja explícitamente a null (enseña al modelo a no rellenar de más).
    """
    campos: dict = {}
    lengua_texto = _nombre_lengua(datos.get("_041a"))
    lengua_original = _nombre_lengua(datos.get("_041h"))

    for clave in claves_esquema:
        valor = datos.get(clave)
        if clave == "lengua_texto":
            valor = lengua_texto
        elif clave == "idioma_original":
            valor = lengua_original

        if valor in (None, "", []):
            campos[clave] = {"valor": None, "confianza": None,
                             "evidencia": None, "zona": None}
            continue

        # Evidencia plausible a partir del propio valor.
        if isinstance(valor, list):
            evidencia = str(valor[0])
        else:
            evidencia = str(valor)
        zona = "preliminares · página 3"
        if clave in {"isbn", "deposito_legal", "titulo_original", "fecha_copyright"}:
            zona = "preliminares · página 4"

        campos[clave] = {
            "valor": valor,
            "confianza": "alta",
            "evidencia": evidencia,
            "zona": zona,
        }
    return {"campos": campos}


def _claves_del_esquema(ruta_esquema: Path) -> list[str]:
    """Lee las claves extraíbles del esquema de Tipo, en orden."""
    with ruta_esquema.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    claves: list[str] = []
    for area in data.get("areas", []):
        for el in area.get("elementos", []):
            if isinstance(el, dict) and el.get("extraible") != "no":
                claves.append(el["clave"])
    return claves


def _describir_caso(datos: dict) -> str:
    """Genera una descripción legible del caso difícil que ilustra el ejemplo."""
    notas = []
    if datos.get("titulo_original") or datos.get("_041h"):
        notas.append("traducción: distinguir título original e idioma original")
    if datos.get("mencion_responsabilidad") and any(
        marca in datos["mencion_responsabilidad"].lower()
        for marca in ("trad", "pról", "prol", "edición de", "ed. de", "ilustr")
    ):
        notas.append("varios responsables con roles distintos")
    if not datos.get("isbn"):
        notas.append("sin ISBN visible")
    if datos.get("serie_transcrita"):
        notas.append("con mención de serie")
    return "; ".join(notas) or "registro bibliográfico estándar"


# ---------------------------------------------------------------------------
# Descarga opcional por SRU (solo con --sru)
# ---------------------------------------------------------------------------

def descargar_sru(consulta: str, maximo: int) -> list[ET.Element]:
    """Descarga registros de la BNE por SRU. Requiere red. Uso opcional."""
    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode({
        "version": "1.1",
        "operation": "searchRetrieve",
        "query": consulta,
        "maximumRecords": str(maximo),
        "recordSchema": "marcxml",
    })
    url = f"{BNE_SRU_URL}?{params}"
    print(f"Descargando de la BNE: {url}", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=30) as resp:
        contenido = resp.read()
    raiz = ET.fromstring(contenido)
    # Los registros vienen anidados dentro de recordData.
    registros = raiz.findall(".//marc:record", MARC_NS)
    print(f"  recibidos {len(registros)} registros", file=sys.stderr)
    return registros


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def registros_de_fichero(ruta: Path) -> list[ET.Element]:
    """Lee uno o varios <record> de un fichero MARCXML."""
    raiz = ET.parse(ruta).getroot()
    if raiz.tag.endswith("record"):
        return [raiz]
    return raiz.findall(".//marc:record", MARC_NS)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Construye ejemplos few-shot para Tipo desde registros MARCXML de la BNE.",
    )
    parser.add_argument("ficheros", nargs="*", type=Path,
                        help="Ficheros MARCXML descargados de la BNE.")
    parser.add_argument("-o", "--salida", type=Path,
                        default=Path("../schemas/ejemplos-monografia.yaml"),
                        help="Fichero YAML de ejemplos a generar.")
    parser.add_argument("--esquema", type=Path,
                        default=Path("../schemas/datos-bibliograficos-monografia.yaml"),
                        help="Esquema de Tipo, para conocer las claves de campo.")
    parser.add_argument("--sru", metavar="CONSULTA",
                        help="Consulta SRU a la BNE (requiere red). Ej: bib.materia=poesia")
    parser.add_argument("--sru-max", type=int, default=5,
                        help="Máximo de registros a traer por SRU (por defecto 5).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra lo que se extraería sin escribir el fichero.")
    args = parser.parse_args()

    if not args.esquema.exists():
        print(f"No se encuentra el esquema: {args.esquema}", file=sys.stderr)
        return 1
    claves = _claves_del_esquema(args.esquema)

    registros: list[ET.Element] = []
    for ruta in args.ficheros:
        if not ruta.exists():
            print(f"Aviso: no existe {ruta}, se omite.", file=sys.stderr)
            continue
        try:
            registros.extend(registros_de_fichero(ruta))
        except ET.ParseError as e:
            print(f"Aviso: {ruta} no es MARCXML válido ({e}), se omite.", file=sys.stderr)

    if args.sru:
        try:
            registros.extend(descargar_sru(args.sru, args.sru_max))
        except Exception as e:
            print(f"No se pudo descargar por SRU ({e}). "
                  f"Continúo solo con los ficheros locales.", file=sys.stderr)

    if not registros:
        print("No hay registros que procesar. Aporta ficheros MARCXML o usa --sru.",
              file=sys.stderr)
        return 1

    ejemplos: list[dict] = []
    for record in registros:
        datos = extraer_datos_registro(record)
        if not datos.get("titulo_principal"):
            continue  # sin título no es un ejemplo útil
        ejemplos.append({
            "descripcion": _describir_caso(datos),
            "texto": construir_texto_simulado(datos),
            "salida": construir_salida(datos, claves),
        })

    print(f"Ejemplos construidos: {len(ejemplos)}", file=sys.stderr)

    if args.dry_run:
        print(yaml.dump({"ejemplos": ejemplos}, allow_unicode=True, sort_keys=False,
                        default_flow_style=False))
        return 0

    cabecera = (
        "# Ejemplos few-shot para Tipo, generados por examples/construir_ejemplos_bne.py\n"
        "# a partir de registros MARCXML de la BNE. Revísalos a mano antes de\n"
        "# empaquetarlos: los ejemplos guían al modelo, conviene que sean impecables.\n"
        "# Este fichero se copia en /app/schemas/ dentro de la imagen de Tipo.\n\n"
    )
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with args.salida.open("w", encoding="utf-8") as f:
        f.write(cabecera)
        yaml.dump({"ejemplos": ejemplos}, f, allow_unicode=True, sort_keys=False,
                  default_flow_style=False)
    print(f"Escrito: {args.salida}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
