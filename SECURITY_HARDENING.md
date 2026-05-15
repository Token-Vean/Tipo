# Hardening técnico

Tipo v0.2.0-beta.4 está diseñado para uso local.

## Controles activos

- Publicación por defecto en `127.0.0.1` mediante Docker Compose.
- Bloqueo de acceso por `Host` no local salvo `ALLOW_NETWORK_EXPOSURE=true`.
- Apagado desde interfaz desactivado automáticamente si `ALLOW_NETWORK_EXPOSURE=true`.
- Contenedor de aplicación sin privilegios elevados.
- `cap_drop: ALL`, `no-new-privileges` y `read_only: true` en la aplicación.
- Validación de PDF, DOCX, TXT e imágenes antes del procesamiento.
- Límites contra imágenes bomba, ZIP bombs en DOCX y PDFs excesivos.
- Sandbox de parsers con timeout y límites de memoria.
- CSRF con token y comprobación de origen para acciones mutadoras.
- Logs sin contenido bibliográfico.
- Ficha técnica de auditoría sin texto completo ni valores propuestos.
- Saneado de nombres de archivo y etiquetas antes de prompt, logs y auditoría.

## Límites

La garantía local depende principalmente de mantener el binding de Docker en `127.0.0.1`. No active `ALLOW_NETWORK_EXPOSURE=true` salvo que añada medidas adicionales de autenticación, segmentación de red y control de acceso.

El fichero `.env` es configuración local de ejecución y no debe subirse al repositorio ni empaquetarse en la release. El instalador lo genera a partir de `.env.example`.
