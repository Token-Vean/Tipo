from app import bibliografico
from app.version import APP_NAME, APP_VERSION


EXPECTED_MAJOR_MINOR = "0.2.0"


def test_app_identity():
    assert APP_NAME == "Tipo"
    assert APP_VERSION.startswith(EXPECTED_MAJOR_MINOR)


def test_isbn_validation():
    assert bibliografico.isbn13_valido("978-84-376-0494-7")
    assert not bibliografico.isbn13_valido("978-84-376-0494-8")


def test_isbd_generation_basic():
    campos = [
        {"clave": "titulo_principal", "valor": "La biblioteca imaginaria"},
        {"clave": "subtitulo", "valor": "ensayos sobre lectura"},
        {"clave": "mencion_responsabilidad", "valor": "Víctor Villapalos"},
        {"clave": "lugar_publicacion", "valor": "Madrid"},
        {"clave": "editor", "valor": "Tipo"},
        {"clave": "fecha_publicacion", "valor": "2026"},
    ]
    isbd = bibliografico.generar_isbd_desde_campos(campos)
    assert "La biblioteca imaginaria : ensayos sobre lectura / Víctor Villapalos" in isbd
    assert "Madrid : Tipo, 2026" in isbd


def test_sanitiza_etiquetas_y_nombres_cortos():
    from app.api import _parsear_etiquetas, _sanear_texto_corto

    assert _sanear_texto_corto("..\\ruta/portada\nmaliciosa.jpg") == ".. ruta portada maliciosa.jpg"
    etiquetas = _parsear_etiquetas('["portada\\ninyectada", "verso/creditos", ""]', 3)
    assert etiquetas == ["portada inyectada", "verso creditos", "imagen_3"]


def test_exportacion_csv_sanea_formula_con_espacios_iniciales():
    from app import exportadores

    payload = {
        "propuesta": {
            "campos": [
                {
                    "id": "titulo",
                    "clave": "titulo_principal",
                    "nombre": "Título",
                    "valor": "  =IMPORTXML(\"http://example.test\")",
                    "confianza": "alta",
                    "evidencia": "=IMPORTXML",
                    "estado_evidencia": "no_verificable",
                }
            ]
        }
    }
    contenido, mime, nombre = exportadores.exportar("csv", payload)
    texto = contenido.decode("utf-8-sig")
    assert mime.startswith("text/csv")
    assert nombre.endswith(".csv")
    assert "'  =IMPORTXML" in texto
