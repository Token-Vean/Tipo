# Seguridad

Tipo está diseñado para uso local. La aplicación mantiene controles local-first: CSRF, cabeceras de seguridad, límite de cuerpo HTTP, validación estricta de archivos, sandbox de parsers y bloqueo de exposición fuera de localhost.

No suba documentos sensibles a modelos o servicios remotos. Por defecto `ALLOW_REMOTE_OLLAMA=false` y `ALLOW_NETWORK_EXPOSURE=false`.
