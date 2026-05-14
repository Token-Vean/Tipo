"""
Segmentación documental por zonas para Tipo.

En catalogación los datos descriptivos de una monografía no están repartidos
por todo el volumen: se concentran en zonas concretas. Este módulo localiza
esas zonas dentro de un documento completo para que Tipo no envíe al modelo
cientos de páginas de OCR, sino solo aquellas donde, por convención
bibliográfica, suele encontrarse la información:

    preliminares  -> cubierta, portada, verso de portada (página de derechos)
                     y, a veces, el índice. Casi siempre en las primeras
                     páginas del volumen.
    finales       -> colofón, depósito legal y datos de impresión. Casi
                     siempre en las últimas páginas.

El cuerpo del libro se descarta deliberadamente: no aporta datos descriptivos
y solo degrada la atención de un modelo local. Subir el libro completo es
ahora el flujo previsto; el usuario no necesita recortar partes a mano.

Este módulo NO decide nada catalográfico: solo recorta y etiqueta. Qué dato
va a qué campo lo decide el modelo, guiado por el prompt del extractor.

Se importa tanto en el proceso principal como en el proceso aislado del
sandbox de parsers, por lo que no debe tener dependencias pesadas a nivel de
módulo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(nombre: str, defecto: int, minimo: int = 0) -> int:
    try:
        return max(minimo, int(os.getenv(nombre, str(defecto))))
    except (TypeError, ValueError):
        return defecto


# Páginas que se consideran "preliminares" y "finales". Son deliberadamente
# generosas: es preferible enviar alguna página de más que perder la portada
# o el colofón. Ajustables por entorno.
PAGINAS_PRELIMINARES = _int_env("ZONA_PAGINAS_PRELIMINARES", 12, minimo=1)
PAGINAS_FINALES = _int_env("ZONA_PAGINAS_FINALES", 6, minimo=0)

# Tope de páginas que se rasterizan para la ruta visión. Une preliminares y
# finales; si la suma supera el tope se recorta dando prioridad a
# preliminares (portada y verso son más decisivos que el colofón).
PAGINAS_ZONA_VISION_MAX = _int_env("ZONA_PAGINAS_VISION_MAX", 14, minimo=1)

# Para documentos sin paginación real (DOCX, TXT) se recorta por caracteres.
CHARS_ZONA_INICIO = _int_env("ZONA_CHARS_INICIO", 8000, minimo=500)
CHARS_ZONA_FINAL = _int_env("ZONA_CHARS_FINAL", 3000, minimo=0)

_ETIQUETA_ZONA = {
    "preliminares": "PRELIMINARES (cubierta, portada, verso de portada, índice)",
    "finales": "FINALES (colofón, depósito legal, datos de impresión)",
    "documento": "DOCUMENTO COMPLETO",
}


@dataclass
class PaginaZonificada:
    """Una página del documento asignada a una zona catalográfica."""

    indice: int   # índice 0-based dentro del documento original
    numero: int   # número de página 1-based, para mostrar al usuario
    zona: str     # "preliminares" | "finales"
    texto: str    # texto OCR de esa página (puede estar vacío)


@dataclass
class Zonificacion:
    """Resultado de segmentar un documento paginado por zonas."""

    paginas: list[PaginaZonificada]   # páginas seleccionadas, en orden
    paginas_totales: int              # total de páginas del documento original

    @property
    def indices_seleccionados(self) -> list[int]:
        return [p.indice for p in self.paginas]

    @property
    def paginas_analizadas(self) -> int:
        return len(self.paginas)

    @property
    def hay_finales(self) -> bool:
        return any(p.zona == "finales" for p in self.paginas)

    def resumen(self) -> dict:
        """Resumen serializable para la ficha técnica de auditoría."""
        prelim = [p.numero for p in self.paginas if p.zona == "preliminares"]
        finales = [p.numero for p in self.paginas if p.zona == "finales"]
        return {
            "estrategia": "zonas",
            "paginas_totales": self.paginas_totales,
            "paginas_analizadas": self.paginas_analizadas,
            "paginas_descartadas": max(0, self.paginas_totales - self.paginas_analizadas),
            "preliminares": prelim,
            "finales": finales,
        }


# =============================================================================
# Segmentación de documentos paginados (PDF)
# =============================================================================

def segmentar_pdf(paginas_texto: list[str]) -> Zonificacion:
    """
    Asigna a zonas las páginas de un PDF a partir de su texto por página.

    No interpreta el contenido: aplica la convención posicional (las primeras
    páginas son preliminares, las últimas son finales). El modelo es quien
    luego localiza el dato concreto dentro de esas zonas.
    """
    total = len(paginas_texto)
    if total == 0:
        return Zonificacion(paginas=[], paginas_totales=0)

    indices_prelim = list(range(min(PAGINAS_PRELIMINARES, total)))

    # Las últimas PAGINAS_FINALES páginas que no solapen con preliminares.
    # En libros muy cortos puede no haber zona final independiente.
    indices_final: list[int] = []
    if PAGINAS_FINALES > 0:
        inicio_final = max(len(indices_prelim), total - PAGINAS_FINALES)
        indices_final = list(range(inicio_final, total))

    paginas: list[PaginaZonificada] = []
    for i in indices_prelim:
        paginas.append(
            PaginaZonificada(indice=i, numero=i + 1, zona="preliminares",
                             texto=paginas_texto[i] or "")
        )
    for i in indices_final:
        paginas.append(
            PaginaZonificada(indice=i, numero=i + 1, zona="finales",
                             texto=paginas_texto[i] or "")
        )
    return Zonificacion(paginas=paginas, paginas_totales=total)


def indices_para_vision(zonif: Zonificacion) -> list[int]:
    """
    Índices de página a rasterizar para la ruta visión, respetando el tope y
    priorizando preliminares sobre finales.
    """
    prelim = [p.indice for p in zonif.paginas if p.zona == "preliminares"]
    finales = [p.indice for p in zonif.paginas if p.zona == "finales"]
    if len(prelim) >= PAGINAS_ZONA_VISION_MAX:
        return prelim[:PAGINAS_ZONA_VISION_MAX]
    hueco = PAGINAS_ZONA_VISION_MAX - len(prelim)
    return prelim + finales[:hueco]


def construir_texto_zonificado(zonif: Zonificacion) -> str:
    """
    Construye un único bloque de texto con las zonas seleccionadas. Cada
    página va precedida de una cabecera legible que el modelo puede citar
    literalmente como 'zona' y 'página' en su evidencia.
    """
    if not zonif.paginas:
        return ""
    bloques: list[str] = []
    zona_actual: str | None = None
    for p in zonif.paginas:
        if p.zona != zona_actual:
            bloques.append(
                f"\n########## ZONA: {_ETIQUETA_ZONA.get(p.zona, p.zona.upper())} ##########"
            )
            zona_actual = p.zona
        cabecera = (
            f"===== {p.zona} · página {p.numero} de {zonif.paginas_totales} ====="
        )
        texto = p.texto.strip()
        if texto:
            bloques.append(f"{cabecera}\n{texto}")
        else:
            bloques.append(f"{cabecera}\n[sin texto extraíble en esta página]")
    return "\n\n".join(bloques).strip()


def etiquetas_para_indices(zonif: Zonificacion, indices: list[int]) -> list[str]:
    """
    Etiqueta legible para cada imagen rasterizada, en el mismo orden que
    `indices`. Sirve para `Entrada.imagenes_etiquetas`.
    """
    por_indice = {p.indice: p for p in zonif.paginas}
    etiquetas: list[str] = []
    for i in indices:
        p = por_indice.get(i)
        if p is None:
            etiquetas.append(f"página {i + 1}")
        else:
            etiquetas.append(f"{p.zona} · página {p.numero}")
    return etiquetas


# =============================================================================
# Segmentación de documentos sin paginación real (DOCX, TXT)
# =============================================================================

def segmentar_texto_plano(texto: str) -> tuple[str, dict]:
    """
    Para documentos sin paginación real. Recorta inicio y final del texto, que
    es donde se concentran portada lógica, créditos y colofón en documentos
    ofimáticos. El cuerpo central se descarta.

    Devuelve (texto_zonificado, resumen_cobertura).
    """
    texto = (texto or "").strip()
    total = len(texto)
    if total == 0:
        return "", {"estrategia": "zonas", "paginas_totales": None,
                    "paginas_analizadas": None, "chars_totales": 0, "chars_analizados": 0}

    if total <= CHARS_ZONA_INICIO + CHARS_ZONA_FINAL:
        bloque = (
            f"########## ZONA: {_ETIQUETA_ZONA['documento']} (documento breve) ##########\n"
            f"===== documento completo =====\n{texto}"
        )
        return bloque, {
            "estrategia": "zonas", "paginas_totales": None, "paginas_analizadas": None,
            "chars_totales": total, "chars_analizados": total,
        }

    inicio = texto[:CHARS_ZONA_INICIO].rstrip()
    bloques = [
        "########## ZONA: INICIO DEL DOCUMENTO (portada lógica, créditos) ##########",
        f"===== inicio del documento =====\n{inicio}",
    ]
    chars_analizados = len(inicio)
    if CHARS_ZONA_FINAL > 0:
        final = texto[-CHARS_ZONA_FINAL:].lstrip()
        bloques.append(
            "########## ZONA: FINAL DEL DOCUMENTO (colofón, créditos finales) ##########"
        )
        bloques.append(f"===== final del documento =====\n{final}")
        chars_analizados += len(final)

    return "\n\n".join(bloques), {
        "estrategia": "zonas", "paginas_totales": None, "paginas_analizadas": None,
        "chars_totales": total, "chars_analizados": chars_analizados,
    }
