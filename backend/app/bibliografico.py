"""
Utilidades bibliográficas ligeras para Tipo v0.1-alpha.

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
    titulo = _txt(campo(campos, "titulo_principal"))
    subtitulo = _txt(campo(campos, "subtitulo"))
    responsabilidad = _txt(campo(campos, "mencion_responsabilidad"))
    edicion = _txt(campo(campos, "mencion_edicion"))
    lugar = _txt(campo(campos, "lugar_publicacion"))
    editor = _txt(campo(campos, "editor"))
    fecha = _txt(campo(campos, "fecha_publicacion"))
    extension = _txt(campo(campos, "extension"))
    ilustraciones = _txt(campo(campos, "ilustraciones"))
    dimensiones = _txt(campo(campos, "dimensiones"))
    serie = _txt(campo(campos, "serie_transcrita"))
    isbn = _txt(campo(campos, "isbn"))

    areas: list[str] = []
    area1 = titulo
    if subtitulo:
        area1 += f" : {subtitulo}"
    if responsabilidad:
        area1 += f" / {responsabilidad}"
    if area1:
        areas.append(area1)
    if edicion:
        areas.append(edicion)
    publicacion = ""
    if lugar:
        publicacion += lugar
    if editor:
        publicacion += (" : " if publicacion else "") + editor
    if fecha:
        publicacion += (", " if publicacion else "") + fecha
    if publicacion:
        areas.append(publicacion)
    fisica = extension
    extras = []
    if ilustraciones:
        extras.append(ilustraciones)
    if dimensiones:
        extras.append(dimensiones)
    if extras:
        fisica += (" : " if fisica else "") + " ; ".join(extras)
    if fisica:
        areas.append(fisica)
    if serie:
        areas.append(f"({serie})")
    if isbn:
        areas.append(f"ISBN {isbn}")
    return ". — ".join(a for a in areas if a).strip()
