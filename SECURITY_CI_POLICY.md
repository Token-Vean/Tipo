# Política de CI de seguridad

Tipo utiliza controles automáticos de seguridad en GitHub Actions. La política distingue entre informes de auditoría y bloqueos de release.

## Bloquean la CI

- Tests fallidos.
- Errores de linting con Ruff.
- Vulnerabilidades detectadas por `pip-audit` en dependencias Python fijadas.
- Presencia accidental de `.env`, bases SQLite locales, `users.json` o secretos en el repositorio.
- Vulnerabilidades `CRITICAL` corregibles detectadas por Trivy en la imagen Docker.

## No bloquean automáticamente, pero generan informe

- Vulnerabilidades `HIGH` en imagen Docker.
- Resultados de Grype sobre la imagen.
- SBOM CycloneDX/SPDX.

## Razonamiento

En imágenes basadas en distribuciones Linux pueden aparecer hallazgos `HIGH` heredados de paquetes del sistema o sin corrección disponible en el momento del análisis. Para la beta, esos hallazgos deben revisarse y documentarse, pero no deben impedir por sí solos que el repositorio mantenga CI verde. Las vulnerabilidades críticas corregibles sí bloquean.
