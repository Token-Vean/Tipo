"""
Exportadores para lotes de Tipo: variantes de colección que agrupan varios
registros bibliográficos en un único fichero descargable.

No modifica exportadores.py: reutiliza sus funciones internas para mantener
una sola fuente de verdad para el formato de un registro.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime
from typing import Any
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, register_namespace, tostring

from . import exportadores
from .bibliografico import generar_isbd_desde_campos
from .version import APP_AGENT

MARC_NS = "http://www.loc.gov/MARC21/slim"
register_namespace("", MARC_NS)


def _record_marcxml_desde_payload(payload: dict) -> Element:
    """Construye un <record> MARCXML desde un payload de libro completo. Es un
    wrapper fino sobre exportadores._construir_record_marcxml, que es la fuente
    única de verdad para la composición de un registro (libro suelto o dentro
    de colección)."""
    campos = exportadores._campos(payload)
    idioma_salida = payload.get("idioma_salida") if isinstance(payload, dict) else None
    return exportadores._construir_record_marcxml(campos, idioma_salida)


def _exportar_marcxml_coleccion(payloads: list[dict], lote_id: str) -> tuple[bytes, str, str]:
    coleccion = Element(f"{{{MARC_NS}}}collection")
    for p in payloads:
        record = _record_marcxml_desde_payload(p)
        coleccion.append(record)
    crudo = tostring(coleccion, encoding="utf-8")
    pretty = minidom.parseString(crudo).toprettyxml(indent="  ", encoding="utf-8")
    data = b"\n".join(linea for linea in pretty.split(b"\n") if linea.strip())
    return data, "application/marcxml+xml; charset=utf-8", f"tipo-lote-{lote_id}-{exportadores._timestamp()}.xml"


def _exportar_marc_txt_coleccion(payloads: list[dict], lote_id: str) -> tuple[bytes, str, str]:
    cabecera = (
        "Tipo — MARC21 en texto plano (lote)\n"
        "Propuesta revisable. No incluye puntos de acceso autorizados ni materias.\n"
        "Indicador en blanco se muestra como '#'.\n"
        f"Lote: {lote_id}    Registros: {len(payloads)}\n"
        "\n"
    )
    bloques: list[str] = []
    for idx, p in enumerate(payloads, 1):
        campos = exportadores._campos(p)
        idioma = p.get("idioma_salida") if isinstance(p, dict) else None
        lineas = exportadores.generar_marc21_texto(campos, idioma)
        titulo = exportadores._txt(exportadores._valor(campos, "titulo_principal")) or f"registro-{idx}"
        bloques.append(f"### Registro {idx}: {titulo}\n" + exportadores.marc21_a_texto_plano(lineas))
    data = (cabecera + "\n\n".join(bloques) + "\n").encode("utf-8")
    return data, "text/plain; charset=utf-8", f"tipo-lote-{lote_id}-marc21-{exportadores._timestamp()}.txt"


def _exportar_isbd_coleccion(payloads: list[dict], lote_id: str) -> tuple[bytes, str, str]:
    cabecera = (
        "Tipo — ISBD derivado (lote)\n"
        "Resultado revisable. No incluye puntos de acceso autorizados ni materias normalizadas.\n"
        f"Lote: {lote_id}    Registros: {len(payloads)}\n"
        "\n"
    )
    bloques: list[str] = []
    for idx, p in enumerate(payloads, 1):
        campos = exportadores._campos(p)
        isbd = p.get("isbd") or generar_isbd_desde_campos(campos)
        titulo = exportadores._txt(exportadores._valor(campos, "titulo_principal")) or f"registro-{idx}"
        bloques.append(f"### Registro {idx}: {titulo}\n{isbd}")
    data = (cabecera + ("\n\n---\n\n".join(bloques)) + "\n").encode("utf-8")
    return data, "text/plain; charset=utf-8", f"tipo-lote-{lote_id}-isbd-{exportadores._timestamp()}.txt"


def _exportar_json_coleccion(payloads: list[dict], lote_id: str) -> tuple[bytes, str, str]:
    limpio = {
        "generado_por": APP_AGENT,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "lote_id": lote_id,
        "registros": len(payloads),
        "nota": "Propuesta descriptiva revisable. No contiene puntos de acceso autorizados.",
        "items": [
            {
                "documento": p.get("documento"),
                "auditoria": p.get("auditoria"),
                "isbd": p.get("isbd") or generar_isbd_desde_campos(exportadores._campos(p)),
                "propuesta": p.get("propuesta"),
            }
            for p in payloads
        ],
    }
    data = json.dumps(limpio, ensure_ascii=False, indent=2).encode("utf-8")
    return data, "application/json; charset=utf-8", f"tipo-lote-{lote_id}-{exportadores._timestamp()}.json"


def _exportar_csv_coleccion(payloads: list[dict], lote_id: str) -> tuple[bytes, str, str]:
    """CSV ancho: una fila por libro, columnas estables formadas por las claves
    presentes en cualquier payload. Cada celda contiene el valor (concatenado
    con ' | ' si es lista)."""
    salida = io.StringIO(newline="")
    # Cabeceras: identificación del libro + columnas por clave
    claves_set: set[str] = set()
    for p in payloads:
        for c in exportadores._campos(p):
            clave = c.get("clave")
            if isinstance(clave, str) and clave and not clave.startswith("isbd_area_"):
                claves_set.add(clave)
    claves_ordenadas = sorted(claves_set)
    cabecera = ["lote_id", "item_peticion", "documento_nombre"] + claves_ordenadas
    writer = csv.writer(salida, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(cabecera)
    for p in payloads:
        campos = exportadores._campos(p)
        valores_por_clave = {}
        for c in campos:
            clave = c.get("clave")
            valor = c.get("valor")
            if isinstance(valor, list):
                valor = " | ".join(str(v) for v in valor)
            valores_por_clave[clave] = exportadores._sanear_csv(valor) if valor is not None else ""
        documento = p.get("documento") or {}
        fila = [
            exportadores._sanear_csv(lote_id),
            exportadores._sanear_csv(p.get("peticion")),
            exportadores._sanear_csv(documento.get("nombre")),
        ]
        for k in claves_ordenadas:
            fila.append(valores_por_clave.get(k, ""))
        writer.writerow(fila)
    data = ("\ufeff" + salida.getvalue()).encode("utf-8")
    return data, "text/csv; charset=utf-8", f"tipo-lote-{lote_id}-{exportadores._timestamp()}.csv"


def _exportar_zip_coleccion(payloads: list[dict], lote_id: str) -> tuple[bytes, str, str]:
    """ZIP con un fichero por libro en cada formato individual + manifiesto.
    Útil para revisión humana libro a libro."""
    buf = io.BytesIO()
    manifiesto = {
        "lote_id": lote_id,
        "generado_por": APP_AGENT,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "registros": [],
    }
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, p in enumerate(payloads, 1):
            slug = exportadores._slug(
                exportadores._txt(exportadores._valor(exportadores._campos(p), "titulo_principal"))
                or f"registro-{idx}"
            )
            base = f"{idx:03d}-{slug}"
            # Por libro: json, csv individual, isbd, marcxml, marc-txt
            for formato in ("json", "csv", "isbd", "marcxml", "marc-txt"):
                contenido, _mime, nombre_archivo = exportadores.exportar(formato, p)
                # Renombramos para no chocar dentro del ZIP
                ext = nombre_archivo.rsplit(".", 1)[-1]
                zf.writestr(f"{base}/{base}.{ext}", contenido)
            manifiesto["registros"].append({
                "orden": idx,
                "item_peticion": p.get("peticion"),
                "documento_nombre": (p.get("documento") or {}).get("nombre"),
                "base": base,
            })
        # Colección global
        for formato, fn in (
            ("marcxml", _exportar_marcxml_coleccion),
            ("marc-txt", _exportar_marc_txt_coleccion),
            ("isbd", _exportar_isbd_coleccion),
            ("json", _exportar_json_coleccion),
            ("csv", _exportar_csv_coleccion),
        ):
            data, _mime, nombre = fn(payloads, lote_id)
            ext = nombre.rsplit(".", 1)[-1]
            zf.writestr(f"coleccion/lote-{formato}.{ext}", data)
        zf.writestr("manifiesto.json", json.dumps(manifiesto, ensure_ascii=False, indent=2).encode("utf-8"))
    return buf.getvalue(), "application/zip", f"tipo-lote-{lote_id}-{exportadores._timestamp()}.zip"


def exportar_lote(formato: str, payloads: list[dict], lote_id: str) -> tuple[bytes, str, str]:
    """Punto de entrada único para la exportación de un lote.

    Devuelve (contenido, mime, nombre_archivo). Lanza ValueError si el formato
    no es soportado.
    """
    if not payloads:
        raise ValueError("No hay registros que exportar.")
    if formato == "json":
        return _exportar_json_coleccion(payloads, lote_id)
    if formato == "csv":
        return _exportar_csv_coleccion(payloads, lote_id)
    if formato == "isbd":
        return _exportar_isbd_coleccion(payloads, lote_id)
    if formato == "marcxml":
        return _exportar_marcxml_coleccion(payloads, lote_id)
    if formato == "marc-txt":
        return _exportar_marc_txt_coleccion(payloads, lote_id)
    if formato == "zip":
        return _exportar_zip_coleccion(payloads, lote_id)
    raise ValueError(f"Formato no soportado: {formato}")
