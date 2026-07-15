# Seguridad

Tipo está diseñado para uso local. La aplicación mantiene controles local-first: CSRF, cabeceras de seguridad, límite de cuerpo HTTP, validación estricta de archivos, sandbox de parsers y bloqueo de exposición fuera de localhost.

No suba documentos sensibles a modelos o servicios remotos. Por defecto `ALLOW_REMOTE_OLLAMA=false` y `ALLOW_NETWORK_EXPOSURE=false`.

## Decisiones de seguridad basadas en la ruta

Los middlewares que toman decisiones de autorización o de exención (autenticación, CSRF, acceso local, cabeceras) usan la ruta ASGI cruda `request.scope["path"]`, no `request.url.path`. Esta última se reconstruye a partir de la cabecera `Host`, que el cliente controla; leerla en un middleware podía provocar divergencia entre la ruta evaluada y la que el router despacha realmente (clase de fallo BadHost / CVE-2026-48710). El uso de `scope["path"]` es la mitigación permanente, complementada por mantener Starlette actualizado (>= 1.0.1).

## Comunicación de vulnerabilidades

Si detecta un problema de seguridad, no lo publique en un issue abierto. Contacte de forma privada con el mantenedor.
