# Política de actualización de dependencias — Tipo

Tipo es una herramienta local que procesa documentos potencialmente sensibles. Por tanto, las dependencias deben tratarse como parte de la superficie de seguridad.

## Frecuencia

- Antes de cada beta o release candidata: ejecutar auditoría completa.
- Mensualmente, si no hay release: revisar vulnerabilidades críticas/altas.
- Inmediatamente: actualizar si una dependencia usada por Tipo publica una vulnerabilidad crítica explotable.

## Procedimiento mínimo antes de publicar

1. Revisar cambios de `backend/requirements.txt` y justificar cualquier subida de versión.
2. Ejecutar tests automatizados.
3. Ejecutar `pip-audit -r backend/requirements.txt`.
4. Construir la imagen local.
5. Ejecutar Trivy y Grype contra la imagen.
6. Generar SBOM CycloneDX y SPDX.
7. Revisar que la release no incluye `.env`, bases SQLite, logs, usuarios ni documentos reales.
8. Verificar que el instalador Windows resuelve automáticamente la imagen base Python a digest y que Ollama sigue fijado por digest.

## Política de versiones

- Python: mantener `3.12-slim` salvo incompatibilidad demostrada. En Windows, el instalador resuelve automáticamente el digest en `.env` antes del build; el usuario final no debe ejecutar comprobaciones manuales.
- Ollama: mantener imagen fijada por digest.
- Dependencias Python: versionado exacto en `requirements.txt`.
- No usar rangos abiertos (`>=`) en release.

## Criterios de aceptación

Una actualización de dependencias solo se acepta si:

- pasan tests;
- no rompe instalación Windows;
- no introduce llamadas externas no documentadas;
- no amplía permisos del contenedor;
- no degrada la extracción bibliográfica básica.
