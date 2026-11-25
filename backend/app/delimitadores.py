"""
Neutralización de delimitadores en el texto que llega al prompt.

El prompt de Tipo separa las partes que escribe la aplicación (instrucciones,
cabeceras de zona, ejemplos) de las que vienen del documento con marcas
fijas: ``<<<DOCUMENTO_INICIO>>>``/``<<<DOCUMENTO_FIN>>>``, las cabeceras
``########## ZONA: … ##########`` y ``===== zona · página N de M =====``, y
los encabezados ``### Fuente: …`` del conjunto de archivos.

Si el texto del documento (o un nombre de archivo o una etiqueta) contiene
esas mismas marcas, puede cerrar el bloque de datos y hacer pasar texto
propio por instrucciones o por una cabecera de zona falsa. Tipo no tiene
herramientas ni acceso a red, así que el riesgo es para la fiabilidad de la
propuesta catalográfica, no para el sistema; aun así se neutraliza aquí, en
un único sitio, como en PlumA 0.7.2.

La sustitución conserva la longitud de cada secuencia y usa caracteres
visualmente parecidos, de modo que el texto sigue siendo legible para el
modelo y para quien revise la evidencia.
"""

from __future__ import annotations

import re

# Marcas de bloque del prompt: tres o más '<' o '>' seguidos.
_ANGULOS_ABRE = re.compile(r"<{3,}")
_ANGULOS_CIERRA = re.compile(r">{3,}")

# Cabeceras de zona y de fuente: tres o más '#' y cinco o más '='.
_ALMOHADILLAS = re.compile(r"#{3,}")
_IGUALES = re.compile(r"={5,}")

_MAX_ETIQUETA = 160


def neutralizar_delimitadores(texto: str | None) -> str:
    """Sustituye las secuencias ``<<<``/``>>>`` por ``‹‹‹``/``›››``."""
    if not texto:
        return ""
    texto = _ANGULOS_ABRE.sub(lambda m: "‹" * len(m.group(0)), texto)
    return _ANGULOS_CIERRA.sub(lambda m: "›" * len(m.group(0)), texto)


def neutralizar_cabeceras(texto: str | None) -> str:
    """Neutraliza delimitadores y marcas de cabecera en texto del documento.

    Se aplica al texto extraído de cada página ANTES de que zonas.py añada sus
    propias cabeceras, para que el documento no pueda fingir una zona o una
    página distinta de la real.
    """
    texto = neutralizar_delimitadores(texto)
    texto = _ALMOHADILLAS.sub(lambda m: "＃" * len(m.group(0)), texto)
    return _IGUALES.sub(lambda m: "═" * len(m.group(0)), texto)


def etiqueta_segura(valor: object, max_len: int = _MAX_ETIQUETA) -> str:
    """Etiqueta de una sola línea apta para el prompt.

    Quita saltos de línea y caracteres de control, neutraliza delimitadores y
    cabeceras, y limita la longitud. Sirve para nombres de archivo y para las
    etiquetas que el usuario o el router asignan a cada imagen.
    """
    texto = "" if valor is None else str(valor)
    texto = "".join(ch if ch.isprintable() else " " for ch in texto)
    texto = " ".join(texto.split())
    texto = neutralizar_cabeceras(texto)
    return texto[:max_len].strip() or "sin_etiqueta"
