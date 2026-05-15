"""
Utilidades bibliográficas ligeras para Tipo v0.2.0-beta.4.

No se crean puntos de acceso autorizados ni se consultan fuentes externas.
"""

from __future__ import annotations

import re
from typing import Any


def _solo_digitos_x(isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def isbn10_valido(isbn: str) -> bool:
    s = _solo_digitos_x(isbn)
    if len(s) != 10:
        return False
    total = 0
    for i, ch in enumerate(s):
        if ch == "X":
            if i != 9:
                return False
            valor = 10
        elif ch.isdigit():
            valor = int(ch)
        else:
            return False
        total += (10 - i) * valor
    return total % 11 == 0


def isbn13_valido(isbn: str) -> bool:
    s = _solo_digitos_x(isbn)
    if len(s) != 13 or not s.isdigit():
        return False
    total = sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(s[:12]))
    check = (10 - (total % 10)) % 10
    return check == int(s[12])


def validar_isbn(valor: Any) -> tuple[bool, str | None]:
    if valor in (None, "", []):
        return True, None
    items = valor if isinstance(valor, list) else [valor]
    invalidos = []
    for item in items:
        s = str(item).strip()
        normalizado = _solo_digitos_x(s)
        if len(normalizado) == 10:
            ok = isbn10_valido(s)
        elif len(normalizado) == 13:
            ok = isbn13_valido(s)
        else:
            ok = False
        if not ok:
            invalidos.append(s)
    if invalidos:
        return False, "ISBN no válido o con dígito de control incorrecto: " + ", ".join(invalidos[:5])
    return True, None


def campo(campos: list[dict], clave: str) -> Any:
    for c in campos:
        if c.get("clave") == clave:
            return c.get("valor")
    return None


def _txt(valor: Any) -> str:
    if valor in (None, "", []):
        return ""
    if isinstance(valor, list):
        return "; ".join(str(v).strip() for v in valor if str(v).strip())
    return str(valor).strip()


def aplicar_validaciones(propuesta: Any) -> None:
    campos = getattr(propuesta, "campos", []) or []
    advertencias = getattr(propuesta, "advertencias", [])
    por_clave = {c.clave: c for c in campos}
    if "isbn" in por_clave:
        ok, msg = validar_isbn(por_clave["isbn"].valor)
        if not ok and msg:
            advertencias.append(msg)
            if por_clave["isbn"].confianza == "alta":
                por_clave["isbn"].confianza = "media"
    if "fecha_publicacion" in por_clave and por_clave["fecha_publicacion"].valor:
        fecha = str(por_clave["fecha_publicacion"].valor)
        anios = [int(x) for x in re.findall(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b", fecha)]
        if any(a > 2100 for a in anios):
            advertencias.append("Fecha de publicación poco plausible; requiere revisión profesional.")


def generar_isbd_desde_campos(campos: list[dict]) -> str:
    """Genera la cadena ISBD completa, área por área, a partir de los campos
    atómicos. Sirve como vista global y como fallback determinista cuando el
    modelo no devuelve los bloques isbd_area_*.
    """
    bloques = ensamblar_bloques_isbd(campos)
    orden = ["isbd_area_0", "isbd_area_1", "isbd_area_2", "isbd_area_4",
             "isbd_area_5", "isbd_area_6", "isbd_area_7", "isbd_area_8"]
    partes = [bloques.get(k) or "" for k in orden]
    return ". — ".join(p for p in partes if p).strip()


def ensamblar_bloques_isbd(campos: list[dict]) -> dict[str, str]:
    """Ensambla cada bloque ISBD a partir de los campos atómicos.

    Devuelve un dict {clave_bloque: cadena_isbd}. Las claves siguen el formato
    isbd_area_<n>. Las áreas para las que no hay datos suficientes se omiten
    o se devuelven como cadena vacía.
    """
    titulo = _txt(campo(campos, "titulo_principal"))
    subtitulo = _txt(campo(campos, "subtitulo"))
    responsabilidad = _txt(campo(campos, "mencion_responsabilidad"))
    edicion = _txt(campo(campos, "mencion_edicion"))
    lugar = _txt(campo(campos, "lugar_publicacion"))
    editor = _txt(campo(campos, "editor"))
    fecha = _txt(campo(campos, "fecha_publicacion"))
    fecha_dl = _txt(campo(campos, "deposito_legal"))  # solo como pista para D.L.
    fecha_cop = _txt(campo(campos, "fecha_copyright"))
    extension = _txt(campo(campos, "extension"))
    ilustraciones = _txt(campo(campos, "ilustraciones"))
    dimensiones = _txt(campo(campos, "dimensiones"))
    serie = _txt(campo(campos, "serie_transcrita"))
    isbn_raw = campo(campos, "isbn")
    dl = _txt(campo(campos, "deposito_legal"))
    notas_extra = _notas_para_area_7(campos)

    bloques: dict[str, str] = {}

    # Área 0 — convención
    tipo_contenido = _txt(campo(campos, "tipo_contenido")) or "Texto (visual)"
    tipo_medio = _txt(campo(campos, "tipo_medio")) or "sin mediación"
    bloques["isbd_area_0"] = f"{tipo_contenido} : {tipo_medio}"

    # Área 1 — Título y mención de responsabilidad
    area1 = titulo
    if subtitulo:
        area1 += f" : {subtitulo}"
    if responsabilidad:
        area1 += f" / {responsabilidad}"
    bloques["isbd_area_1"] = area1

    # Área 2 — Edición
    bloques["isbd_area_2"] = edicion

    # Área 4 — Lugar : Editor, Fecha
    fecha_para_area4 = fecha
    if not fecha_para_area4 and fecha_dl:
        anio = _anio_de(fecha_dl)
        if anio:
            fecha_para_area4 = f"D.L. {anio}"
    if not fecha_para_area4 and fecha_cop:
        anio = _anio_de(fecha_cop)
        if anio:
            fecha_para_area4 = f"cop. {anio}"
    publicacion = ""
    if lugar:
        publicacion += lugar
    if editor:
        publicacion += (" : " if publicacion else "") + _limpiar_editor(editor)
    if fecha_para_area4:
        publicacion += (", " if publicacion else "") + fecha_para_area4
    bloques["isbd_area_4"] = publicacion

    # Área 5 — Descripción física
    fisica = extension
    extras = []
    if ilustraciones:
        extras.append(ilustraciones)
    if extras:
        fisica += (" : " if fisica else "") + " ; ".join(extras)
    if dimensiones:
        fisica += (" ; " if fisica else "") + dimensiones
    bloques["isbd_area_5"] = fisica

    # Área 6 — Serie entre paréntesis
    bloques["isbd_area_6"] = f"({serie})" if serie else ""

    # Área 7 — Notas
    bloques["isbd_area_7"] = ". ".join(n for n in notas_extra if n)

    # Área 8 — ISBN y D.L., uno por línea
    lineas = []
    if isbn_raw:
        items = isbn_raw if isinstance(isbn_raw, list) else [isbn_raw]
        for item in items:
            s = str(item).strip()
            if s:
                lineas.append(f"ISBN {s}")
    if dl:
        lineas.append(f"D.L. {dl}")
    bloques["isbd_area_8"] = "\n".join(lineas)

    return bloques


def _notas_para_area_7(campos: list[dict]) -> list[str]:
    notas = []
    for clave in ("nota_general", "nota_bibliografia", "nota_lengua", "resumen"):
        v = _txt(campo(campos, clave))
        if v:
            notas.append(v)
    return notas


def _limpiar_editor(editor: str) -> str:
    """Elimina prefijos como 'Editorial' o 'Ediciones' al transcribir."""
    s = editor.strip()
    for prefijo in ("Editorial ", "Ediciones ", "Editor "):
        if s.lower().startswith(prefijo.lower()):
            return s[len(prefijo):].strip()
    return s


def _anio_de(texto: str) -> str | None:
    m = re.search(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b", texto or "")
    return m.group(0) if m else None


def aplicar_bloques_isbd_a_propuesta(propuesta: Any) -> None:
    """Rellena los campos isbd_area_* que el modelo no haya cumplimentado,
    reconstruyéndolos de forma determinista a partir de los campos atómicos.

    Si el modelo SÍ devolvió un bloque, se respeta. Si la versión determinista
    difiere de la del modelo, se añade una advertencia para revisión humana.
    """
    campos = getattr(propuesta, "campos", []) or []
    advertencias = getattr(propuesta, "advertencias", [])
    por_clave = {c.clave: c for c in campos}
    bloques_det = ensamblar_bloques_isbd([c.__dict__ for c in campos])
    for clave_bloque, cadena_det in bloques_det.items():
        campo_obj = por_clave.get(clave_bloque)
        if campo_obj is None:
            continue
        if campo_obj.valor in (None, "", []):
            if cadena_det:
                campo_obj.valor = cadena_det
                campo_obj.estado_evidencia = "no_verificable"
                campo_obj.confianza = campo_obj.confianza or "media"
                campo_obj.evidencia = (
                    campo_obj.evidencia
                    or "Bloque reconstruido a partir de los campos atómicos."
                )
        else:
            # El modelo devolvió un bloque. Si difiere mucho del determinista,
            # avisamos para que el profesional decida.
            if cadena_det and _bloques_difieren(str(campo_obj.valor), cadena_det):
                advertencias.append(
                    f"{clave_bloque}: el bloque ISBD propuesto por el modelo "
                    f"difiere del reconstruido de los campos atómicos; revisa."
                )


def _bloques_difieren(a: str, b: str) -> bool:
    norm_a = " ".join(a.split())
    norm_b = " ".join(b.split())
    if not norm_a or not norm_b:
        return False
    return norm_a.lower() != norm_b.lower()
