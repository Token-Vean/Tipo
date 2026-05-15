<p align="center">
  <img src="Tipo.png" alt="Tipo" width="600">
</p>

# Tipo

**Tipo** es una aplicación local de apoyo a la precatalogación de monografías impresas. A partir de imágenes, PDF, DOCX o textos facilitados por el usuario, extrae datos bibliográficos observables y propone campos descriptivos estructurados para revisión profesional.

Tipo es una aplicación independiente. Reutiliza componentes técnicos locales y de seguridad desarrollados previamente, pero no es un fork de otro repositorio ni conserva lógica archivística ajena a su finalidad bibliográfica.

## Principios de diseño

- Funcionamiento **local-first** mediante Docker y Ollama.
- Publicación por defecto solo en `127.0.0.1` / `localhost`.
- Sin consultas a catálogos externos.
- Sin creación de puntos de acceso autorizados.
- Sin asignación de materias normalizadas.
- Sin integración ni escritura sobre SIGB externos.
- Resultado siempre revisable por un profesional.
- Autenticación local con usuario y contraseña desde la versión `0.2.0-beta.4`.

## Alcance de v0.2.0-beta.4

- Monografías impresas modernas.
- Entrada: libro completo en PDF o conjunto de imágenes/documentos relevantes.
- Segmentación por zonas: Tipo analiza preliminares y finales, y evita enviar el cuerpo completo del libro al modelo.
- Salida: propuesta de campos descriptivos, vista ISBD, JSON, CSV, MARC21 TXT y MARCXML descriptivo inicial.
- Auditoría técnica ligera, configurable para incluir o no hash documental.
- Gestión local de usuarios: primer arranque con creación de usuario administrador, cambio de contraseña, creación de usuarios, desactivación, eliminación y restablecimiento por administrador.
- Recuperación local del administrador desde el panel Windows en caso de pérdida de contraseña.

## Instalación rápida en Windows

Para usuarios no técnicos, descomprima la release y ejecute:

```text
Instalar Tipo.bat
```

Se abrirá una ventana desde la que se puede:

- instalar o actualizar;
- iniciar Tipo;
- detener Tipo;
- desinstalar contenedores/volúmenes;
- abrir la herramienta en el navegador;
- consultar estado y logs;
- recuperar acceso de administrador si se pierde la contraseña.

El instalador comprueba Docker Desktop. Si Docker no está instalado o no está arrancado, muestra instrucciones y detiene la instalación. También comprueba si hay Ollama nativo en `localhost:11434`. Si lo detecta, utiliza ese Ollama; si no lo detecta, usa Ollama dentro de Docker como instalación autocontenida.

## Instalación en Linux/macOS

```bash
chmod +x instalar.sh detener.sh desinstalar.sh
./instalar.sh
```

La aplicación se abre por defecto en:

```text
http://localhost:8082
```

En macOS, Docker Desktop debe estar instalado y en ejecución. Ollama nativo es opcional; si no existe, Tipo puede usar Ollama dentro de Docker.

## Primer arranque y autenticación

En el primer acceso, Tipo solicita crear un usuario administrador local. La contraseña no se guarda en claro: se almacena como hash PBKDF2-HMAC-SHA256 en el volumen local `tipo-data`.

La autenticación está pensada como capa adicional para instalaciones personales/locales. No convierte Tipo en una aplicación multiusuario institucional lista para red. Para exponerla en red habría que añadir controles adicionales: TLS, reverse proxy, política de usuarios, copias de seguridad, registros de auditoría y endurecimiento de infraestructura.

## Configuración

La configuración local se crea desde `.env.example` y queda en `.env`. El fichero `.env` está excluido del repositorio y no debe publicarse.

Variables relevantes:

```text
PUERTO=8082
MODELO_BASE=gemma4:e4b
MODELO_NOMBRE=gemma4:e4b
TIPO_CREAR_MODELO_DERIVADO=false
TIPO_AUTH_DISABLED=false
ALLOW_REMOTE_OLLAMA=false
ALLOW_NETWORK_EXPOSURE=false
PERMITIR_APAGADO_UI=true
```

La lista desplegable de modelos muestra los modelos ya descargados en Ollama. La imagen Docker de Ollama está fijada por digest en `.env.example` y `docker-compose.yml`. En Windows, el instalador resuelve automáticamente la imagen base `python:3.12-slim` a digest y la guarda en `.env` antes de construir la imagen, sin intervención del usuario final.

## Seguridad local

Tipo debe ejecutarse como herramienta local. La publicación Docker queda limitada a `127.0.0.1`. No active `ALLOW_NETWORK_EXPOSURE=true` salvo que vaya a añadir controles adicionales de autenticación, red y cifrado.

Antes de subir cambios al repositorio, ejecute:

```bash
scripts/comprobar_antes_de_subir.sh
```

En Windows puede ejecutar:

```text
scripts\comprobar_antes_de_subir.bat
```

## Advertencia profesional

Tipo no sustituye el juicio catalográfico. Los datos propuestos deben revisarse antes de incorporarse a cualquier catálogo o sistema bibliotecario.

## Prompt técnico del modelo

El prompt usado para solicitar la extracción bibliográfica al modelo local puede revisarse en:

```text
docs/PROMPT_MODELO_TIPO.md
```


## Novedades 0.2.0-beta.4

- Instalador/panel Windows con detección reforzada de Docker y Ollama.
- Apagado desde la interfaz con confirmación y pantalla final.
- Gestión local de usuarios en SQLite con migración desde `users.json`.
- Seguridad de autenticación reforzada con bloqueo temporal tras intentos fallidos.
- Selector de modelos Ollama con metadatos de tamaño, familia, fecha, parámetros, cuantización y capacidades esperadas.
- Diagnóstico operativo desde la interfaz.
- `.dockerignore`, scripts de auditoría (`pip-audit`, Trivy, Grype) y generación SBOM CycloneDX/SPDX.
- Política de actualización de dependencias en `DEPENDENCY_UPDATE_POLICY.md`.

> Alcance funcional de la beta: catalogación asistida de monografía moderna impresa. No está optimizada para manuscritos, fondo antiguo, publicaciones seriadas ni recursos electrónicos.
