# Tipo v0.1.1-alpha

Versión de corrección temprana de Tipo.

## Cambios principales

- Añadido selector visible de idioma de interfaz en la cabecera.
- La propuesta bibliográfica se solicita al modelo en el idioma seleccionado para la interfaz.
- Mejorado el botón de apagado con estado visible, gestión de error y compatibilidad CSRF más robusta para peticiones same-origin.
- Ajustada la política `Referrer-Policy` a `same-origin` para evitar bloqueos innecesarios en operaciones locales protegidas.
- Añadida documentación del prompt técnico usado por el modelo: `docs/PROMPT_MODELO_TIPO.md`.

## Límites mantenidos

Tipo sigue siendo una aplicación local-first: no consulta catálogos externos, no crea puntos de acceso autorizados, no asigna materias normalizadas y no opera sobre SIGB externos.
