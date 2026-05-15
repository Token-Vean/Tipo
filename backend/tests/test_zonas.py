"""
Tests de la lógica nueva de la v0.2: segmentación por zonas y lectura
tolerante de la respuesta del modelo.

No requieren Ollama ni red: prueban la lógica determinista que decide qué
parte del libro se envía al modelo y cómo se interpreta lo que devuelve.

Ejecutar con:  pytest backend/tests/test_zonas.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite importar app.* al ejecutar pytest desde la raíz del repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import zonas  # noqa: E402
from app.extractor import _extraer_json  # noqa: E402


# ---------------------------------------------------------------------------
# Segmentación de PDF por zonas
# ---------------------------------------------------------------------------

def test_segmentar_pdf_libro_largo_descarta_cuerpo():
    paginas = ["portada"] + ["cuerpo"] * 300 + ["colofon"] * 5
    z = zonas.segmentar_pdf(paginas)
    assert z.paginas_totales == 306
    # Solo se analizan preliminares + finales, nunca el cuerpo.
    assert z.paginas_analizadas == zonas.PAGINAS_PRELIMINARES + zonas.PAGINAS_FINALES
    assert z.paginas_analizadas < z.paginas_totales
    zonas_vistas = {p.zona for p in z.paginas}
    assert zonas_vistas == {"preliminares", "finales"}


def test_segmentar_pdf_no_solapa_preliminares_y_finales():
    # Libro corto: las páginas finales no deben repetir las preliminares.
    paginas = ["p"] * 10
    z = zonas.segmentar_pdf(paginas)
    indices = z.indices_seleccionados
    assert len(indices) == len(set(indices)), "hay páginas duplicadas entre zonas"


def test_segmentar_pdf_vacio():
    z = zonas.segmentar_pdf([])
    assert z.paginas_totales == 0
    assert z.paginas == []
    assert zonas.construir_texto_zonificado(z) == ""


def test_indices_para_vision_respeta_tope_y_prioriza_preliminares():
    paginas = ["x"] * 500
    z = zonas.segmentar_pdf(paginas)
    indices = zonas.indices_para_vision(z)
    assert len(indices) <= zonas.PAGINAS_ZONA_VISION_MAX
    # Las primeras posiciones deben ser preliminares (índices bajos).
    assert indices[0] < zonas.PAGINAS_PRELIMINARES


def test_texto_zonificado_incluye_cabeceras_citables():
    # 52 páginas: 12 preliminares, 34 de cuerpo central y 6 finales.
    # El marcador de cuerpo central solo aparece en páginas 13-46; por tanto,
    # debe quedar fuera del texto enviado al modelo.
    paginas = (
        ["TÍTULO DEL LIBRO"]
        + [f"PRELIMINAR {i}" for i in range(2, 13)]
        + ["CUERPO CENTRAL"] * 34
        + [f"FINAL {i}" for i in range(47, 52)]
        + ["COLOFÓN"]
    )
    z = zonas.segmentar_pdf(paginas)
    texto = zonas.construir_texto_zonificado(z)
    # El modelo debe poder citar zona y página a partir de estas cabeceras.
    assert "===== preliminares · página 1 de 52 =====" in texto
    assert "ZONA: PRELIMINARES" in texto
    assert "ZONA: FINALES" in texto
    assert "TÍTULO DEL LIBRO" in texto
    assert "COLOFÓN" in texto
    assert "CUERPO CENTRAL" not in texto  # el cuerpo central se descarta


def test_etiquetas_para_indices_coherentes():
    paginas = ["a"] * 100
    z = zonas.segmentar_pdf(paginas)
    indices = zonas.indices_para_vision(z)
    etiquetas = zonas.etiquetas_para_indices(z, indices)
    assert len(etiquetas) == len(indices)
    assert all("página" in e for e in etiquetas)


# ---------------------------------------------------------------------------
# Segmentación de texto plano (DOCX, TXT)
# ---------------------------------------------------------------------------

def test_segmentar_texto_plano_documento_largo_recorta():
    texto = "INICIO " * 3000 + "RELLENO " * 5000 + "FINAL " * 1000
    recortado, cob = zonas.segmentar_texto_plano(texto)
    assert cob["chars_analizados"] < cob["chars_totales"]
    assert "INICIO DEL DOCUMENTO" in recortado
    assert "FINAL DEL DOCUMENTO" in recortado


def test_segmentar_texto_plano_documento_breve_intacto():
    texto = "Un documento corto que cabe entero."
    recortado, cob = zonas.segmentar_texto_plano(texto)
    assert cob["chars_analizados"] == cob["chars_totales"]
    assert "documento completo" in recortado


def test_segmentar_texto_plano_vacio():
    recortado, cob = zonas.segmentar_texto_plano("")
    assert recortado == ""
    assert cob["chars_totales"] == 0


# ---------------------------------------------------------------------------
# Lectura tolerante de la respuesta del modelo
# ---------------------------------------------------------------------------

def test_extraer_json_quita_fences_markdown():
    bruto = '```json\n{"campos": {"isbn": {"valor": null}}}\n```'
    limpio, truncado = _extraer_json(bruto)
    assert not truncado
    assert limpio.startswith("{") and limpio.endswith("}")


def test_extraer_json_ignora_ruido_alrededor():
    bruto = 'Claro, aquí tienes el resultado: {"campos": {}} Espero que sirva.'
    limpio, truncado = _extraer_json(bruto)
    assert not truncado
    assert limpio == '{"campos": {}}'


def test_extraer_json_detecta_truncamiento():
    bruto = '{"campos": {"titulo": {"valor": "La casa del'
    _, truncado = _extraer_json(bruto)
    assert truncado


def test_extraer_json_ignora_llaves_dentro_de_cadenas():
    # Una llave de cierre dentro de un string no debe cerrar el objeto.
    bruto = '{"campos": {"nota": {"valor": "contiene } una llave"}}}'
    limpio, truncado = _extraer_json(bruto)
    assert not truncado
    import json
    json.loads(limpio)  # debe ser JSON válido


def test_extraer_json_sin_objeto():
    limpio, truncado = _extraer_json("no hay json aquí")
    assert truncado
