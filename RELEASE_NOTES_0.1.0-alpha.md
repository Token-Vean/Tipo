# Tipo v0.1.0-alpha

Primera versión base de Tipo como aplicación independiente.

## Incluye

- Marca Tipo integrada.
- Interfaz local con subida múltiple de fuentes del libro.
- Etiquetado de imágenes: portada, verso de portada, cubierta, contracubierta, lomo, colofón, índice, bibliografía u otra.
- Extracción bibliográfica atómica para monografías impresas modernas.
- Esquema inicial `datos-bibliograficos-monografia.yaml`.
- Vista ISBD derivada.
- Exportación JSON, CSV, ISBD TXT y MARCXML descriptivo inicial.
- Ficha técnica de auditoría sin texto del libro ni valores propuestos.
- Seguridad local-first: CSRF, cabeceras de seguridad, sandbox de parsers, límites de tamaño y bloqueo de exposición fuera de localhost.

## Excluido deliberadamente

- Puntos de acceso autorizados.
- Registros de autoridad.
- Materias normalizadas.
- Clasificación automática.
- Consulta de catálogos externos.
- Integración o escritura sobre SIGB.
