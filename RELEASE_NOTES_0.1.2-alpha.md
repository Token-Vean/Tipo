# Tipo v0.1.2-alpha

Versión de endurecimiento y limpieza de paquete.

## Cambios principales

- Eliminado el fichero `.env` del paquete de repositorio y de la release. La configuración local se crea a partir de `.env.example` durante la instalación.
- Refuerzo del apagado desde la interfaz: queda bloqueado automáticamente si `ALLOW_NETWORK_EXPOSURE=true`.
- Saneado de nombres de archivo y etiquetas antes de introducirlos en prompt, auditoría y logs.
- Limpieza de cachés Python (`__pycache__`, `*.pyc`) y artefactos locales antes de empaquetar.
- Añadidas pruebas básicas para saneado de metadatos de entrada y exportación CSV frente a fórmula.

## Recordatorio de seguridad

Tipo está diseñado para uso local. La configuración segura depende de mantener el binding de Docker en `127.0.0.1`. No active `ALLOW_NETWORK_EXPOSURE=true` salvo que añada controles adicionales de autenticación y red.
