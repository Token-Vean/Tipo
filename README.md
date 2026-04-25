# Tipo

**Tipo** es una aplicación local de apoyo a la precatalogación de monografías impresas. A partir de imágenes o documentos facilitados por el usuario, extrae datos bibliográficos observables y propone campos descriptivos estructurados para revisión profesional.

Tipo es una aplicación independiente. Reutiliza componentes técnicos locales y de seguridad desarrollados previamente, pero no es un fork de GitHub ni conserva lógica archivística.

## Principios de diseño

- Funcionamiento local-first mediante Docker y Ollama.
- Sin consultas a catálogos externos.
- Sin creación de puntos de acceso autorizados.
- Sin asignación de materias normalizadas.
- Sin integración ni escritura sobre SIGB externos.
- Resultado siempre revisable por un profesional.

## Alcance de v0.1-alpha

- Monografías impresas modernas.
- Entrada: varias imágenes o documentos del libro: portada, verso de portada, cubierta, contracubierta, lomo, colofón, índice u otras fuentes.
- Salida: propuesta de campos descriptivos, vista ISBD derivada, JSON, CSV y MARCXML descriptivo inicial.
- Auditoría técnica ligera sin almacenar contenido documental.

## Instalación rápida

En Windows, ejecutar `instalar.bat`.

En Linux/macOS:

```bash
chmod +x instalar.sh
./instalar.sh
```

La aplicación se abre por defecto en `http://localhost:8082`.

## Advertencia profesional

Tipo no sustituye el juicio catalográfico. Los datos propuestos deben revisarse antes de incorporarse a cualquier catálogo o sistema bibliotecario.


## Prompt técnico del modelo

El prompt usado para solicitar la extracción bibliográfica al modelo local puede revisarse en `docs/PROMPT_MODELO_TIPO.md`.


## Seguridad local

Tipo debe ejecutarse como herramienta local. La publicación Docker queda limitada a `127.0.0.1`. No active `ALLOW_NETWORK_EXPOSURE=true` salvo que vaya a añadir controles adicionales de autenticación y red. El fichero `.env` es configuración local y no debe subirse al repositorio.
