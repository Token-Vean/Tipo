<p align="center">
  <img src="Tipo.png" alt="Tipo" width="600">
</p>

# Tipo

**Tipo** es un asistente local de IA para apoyar la **precatalogación de monografías impresas modernas**. A partir de imágenes, PDF, DOCX o textos facilitados por el usuario, extrae datos bibliográficos observables y propone una descripción estructurada para revisión profesional.

> Sube uno o varios libros, revisa la propuesta bibliográfica y exporta los resultados en MARCXML, MARC21 texto, ISBD, JSON o CSV, sin enviar los documentos a servicios externos.

**Versión actual:** `0.3.1-beta.1`  
**Estado:** beta, apta para entornos profesionales con supervisión.  
**Ámbito:** monografía moderna impresa.  
**Modelo de uso:** local-first, con Docker y Ollama.

Tipo es una aplicación independiente. Reutiliza componentes técnicos locales y de seguridad desarrollados previamente, pero no es un fork de otro repositorio ni conserva lógica archivística ajena a su finalidad bibliográfica.

---

## Qué permite hacer

- Analizar un libro individual a partir de PDF, imágenes, DOCX o texto.
- Procesar **lotes de libros** en una sola operación.
- Trabajar con tres modos de subida:
  - **Un solo libro**: varias páginas o imágenes de un mismo título.
  - **Varios libros — uno por fichero**: un PDF o fichero por cada libro.
  - **Varios libros — uno por ZIP**: un ZIP por libro, con varias imágenes o documentos dentro.
- Revisar una propuesta bibliográfica antes de exportarla.
- Consultar una vista ISBD generada automáticamente.
- Exportar registros en:
  - MARCXML;
  - MARC21 texto;
  - ISBD;
  - JSON;
  - CSV;
  - ZIP de lote con los resultados por libro y la colección agregada.
- Usar modelos locales descargados en Ollama.
- Mantener los documentos en el propio equipo del usuario, sin consultas automáticas a servicios externos.

---

## Principios de diseño

- Funcionamiento **local-first** mediante Docker y Ollama.
- Publicación por defecto solo en `127.0.0.1` / `localhost`.
- Sin envío de documentos a plataformas comerciales en la nube.
- Sin consultas automáticas a catálogos externos.
- Sin creación de puntos de acceso autorizados.
- Sin asignación de materias normalizadas.
- Sin integración ni escritura directa sobre SIGB externos.
- Resultado siempre revisable por un profesional.
- Autenticación local con usuario y contraseña.
- Exportación orientada a reutilización profesional, especialmente mediante MARCXML y MARC21 texto.

---

## Alcance funcional de la versión `0.3.0-beta.1`

Tipo está orientado a la **catalogación asistida de monografías impresas modernas**. No está optimizado para manuscritos, fondo antiguo, publicaciones seriadas ni recursos electrónicos.

En esta versión, el flujo principal se ha ampliado desde el análisis de un libro individual al **tratamiento por lotes**. Esto permite subir colecciones completas de libros y obtener resultados separados por cada obra, junto con exportaciones agregadas del conjunto.

La aplicación analiza zonas bibliográficamente relevantes —especialmente preliminares y partes finales— y evita enviar el cuerpo completo del libro al modelo cuando no es necesario. El objetivo es reducir carga, tiempo de procesamiento y ruido documental.

La salida incluye propuesta descriptiva, vista ISBD, JSON, CSV, MARC21 TXT y MARCXML. En `0.3.0-beta.1` se refuerza la calidad estructural de los registros MARC21 mediante la generación de campos y normalizaciones más adecuados para importación en SIGB.

---

## Novedades principales de `0.3.0-beta.1`

### Procesamiento por lotes

La mejora principal de esta versión es la posibilidad de procesar varios libros en una sola operación.

El usuario puede elegir entre tres modos de subida:

1. **Un solo libro**: útil cuando se aportan varias páginas o imágenes de una misma obra.
2. **Varios libros — uno por fichero**: útil cuando cada PDF o documento corresponde a un libro distinto.
3. **Varios libros — uno por ZIP**: útil cuando cada libro está formado por varias imágenes o documentos agrupados en un ZIP independiente.

Durante el procesamiento, Tipo muestra un navegador de lote con indicadores por libro: pendiente, en curso, listo, error o cancelado. También permite moverse entre libros mediante los chips numerados de la interfaz y con las teclas de dirección izquierda/derecha.

Cuando el primer resultado está disponible, ya se pueden descargar exportaciones del lote. El ZIP completo incluye una carpeta por libro y una colección agregada.

### MARC21 más importable

A partir de esta versión, los registros generados incluyen mejoras estructurales relevantes:

- campo `008` de 40 caracteres;
- campo `041` cuando procede;
- limpieza de puntuación ISBD dentro de subcampos MARC;
- normalización de la mención de edición a forma RDA;
- indicadores `245` y `264` configurados de forma más adecuada;
- subcampos más limpios para facilitar la importación y revisión posterior.

La validación realizada hasta esta beta es **estructural**. Es decir, se ha comprobado que los registros cumplen requisitos formales más sólidos respecto a la beta anterior. La validación funcional contra instalaciones reales de SIGB queda pendiente para una versión posterior.

---

## Lo que Tipo no hace

Tipo no sustituye el trabajo catalográfico profesional. En particular:

- **No** crea puntos de acceso autorizados `1XX`, `6XX` o `7XX`.
- **No** consulta catálogos externos ni ficheros de autoridades.
- **No** asigna materias normalizadas.
- **No** valida autoridades personales, corporativas o de materia.
- **No** escribe directamente en Koha, Aleph, Symphony, Absys NET u otros SIGB.
- **No** convierte automáticamente una propuesta en un registro definitivo.

El profesional debe revisar, corregir, completar y validar los resultados antes de incorporarlos a cualquier catálogo.

---

## Instalación rápida en Windows

Para usuarios no técnicos, descargue y descomprima el `.zip` de la release. Después ejecute:

```text
Instalar Tipo.bat
```

Se abrirá una ventana desde la que se puede:

- instalar o actualizar Tipo;
- iniciar la aplicación;
- detener la aplicación;
- desinstalar contenedores y volúmenes;
- abrir Tipo en el navegador;
- consultar estado y logs;
- recuperar el acceso de administrador si se pierde la contraseña.

El instalador comprueba Docker Desktop. Si Docker no está instalado o no está arrancado, muestra instrucciones y detiene la instalación.

### Ollama del equipo u Ollama en Docker

- **Si hay un Ollama arrancado en el equipo** (`127.0.0.1:11434`), Tipo lo reutiliza con los modelos que ya tenga, siempre que sea la **versión 0.35.0 o posterior**. Todas las anteriores están afectadas por un aviso de seguridad (CVE-2026-103663, path traversal en la descarga de modelos).
- **Si ese Ollama es anterior a 0.35.0** o no informa de su versión, el instalador se detiene y pide actualizarlo desde [ollama.com/download](https://ollama.com/download). Los modelos se conservan al actualizar. No se cambia a Ollama en Docker, porque el antiguo seguiría funcionando y vulnerable en el equipo.
- **Si no hay Ollama en el equipo**, Tipo usa Ollama dentro de Docker (`ollama/ollama:0.40.17`, la misma versión que PlumA, con `OLLAMA_NO_CLOUD=1`) y descarga el modelo la primera vez.

El backend repite la comprobación al arrancar y antes de cada análisis: si alguien sustituye el Ollama por uno antiguo con Tipo en marcha, no se le envía ningún documento.

### Puerto

Tipo se abre en `http://127.0.0.1:8769`. PlumA usa el `8082`, así que se pueden tener las dos abiertas a la vez. Si un `.env` antiguo de Tipo tenía `PUERTO=8082`, el instalador lo cambia a `8769`; no se admite el `8082`. Si el puerto está ocupado por otra aplicación, el instalador se detiene en lugar de arrancar a medias, y solo abre el navegador cuando quien responde es Tipo.

---

## Instalación en Linux/macOS

```bash
chmod +x instalar.sh detener.sh desinstalar.sh
./instalar.sh
```

La aplicación se abre por defecto en:

```text
http://localhost:8769
```

En macOS, Docker Desktop debe estar instalado y en ejecución. Ollama nativo es opcional; si no existe, Tipo puede usar Ollama dentro de Docker.

### Linux y Ollama del equipo (nota de seguridad)

En Linux, el instalador usa por defecto **Ollama dentro de Docker**, aunque haya un Ollama instalado en el equipo (si es anterior a 0.35.0, avisa de que conviene actualizarlo). Con Docker Engine, el contenedor de Tipo llega al equipo por la IP del puente de Docker (normalmente `172.17.0.1`), mientras que Ollama escucha por defecto solo en `127.0.0.1`.

Si quiere usar su propio Ollama:

1. Haga que escuche en el puente de Docker, **no en todas las interfaces**: `OLLAMA_HOST=172.17.0.1:11434`.
2. Instale con `TIPO_PERFIL=external ./instalar.sh`. El instalador comprueba que ese Ollama es la versión 0.35.0 o posterior (en `http://172.17.0.1:11434`; otra dirección con `TIPO_OLLAMA_PUENTE`).

**No use nunca `OLLAMA_HOST=0.0.0.0`.** Ollama no tiene autenticación: con ese valor, cualquier equipo de la red local puede usarlo, descargar modelos en él o leer lo que procesa.

En cualquier sistema, si usa su propio Ollama, conviene activar el modo solo local que documenta Ollama (`OLLAMA_NO_CLOUD=1`) para que no pueda usar modelos en la nube. El Ollama que Tipo instala en Docker ya lo trae activado.

---

## Actualización desde `0.2.0-beta.7`

Si ya se utilizaba la versión `0.2.0-beta.7`, puede actualizarse sin migración manual de datos.

1. Detenga el servicio:

```bash
docker compose down
```

2. Sustituya el código por la nueva release o ejecute de nuevo el instalador.
3. Arranque la aplicación:

```bash
docker compose up -d
```

4. En el primer arranque deberían aparecer mensajes similares a estos en los logs:

```text
INFO  app.lotes: Recuperación de arranque: 0 items pendientes reencolados
INFO  app.lotes: Worker de lotes iniciado
```

5. Refresque el navegador con **Ctrl + F5** en Windows/Linux o **Cmd + Shift + R** en macOS.

No hace falta migrar datos. Las tablas de lote se crean en el mismo SQLite y los `result.json` antiguos siguen siendo válidos.

---

## Primer arranque y autenticación

En el primer acceso, Tipo solicita crear un usuario administrador local. La contraseña no se guarda en claro: se almacena como hash PBKDF2-HMAC-SHA256 en el volumen local `tipo-data`.

La autenticación está pensada como capa adicional para instalaciones personales o locales. No convierte Tipo en una aplicación multiusuario institucional lista para exposición en red. Para exponerla fuera de `localhost` habría que añadir controles adicionales: TLS, reverse proxy, política de usuarios, copias de seguridad, registros de auditoría, endurecimiento de infraestructura y revisión de riesgos.

---

## Configuración

La configuración local se crea desde `.env.example` y queda en `.env`. El fichero `.env` está excluido del repositorio y no debe publicarse.

Variables principales:

```text
PUERTO=8769
MODELO_BASE=gemma4:e4b
MODELO_NOMBRE=gemma4:e4b
TIPO_CREAR_MODELO_DERIVADO=false
TIPO_LOTE_RETENCION_DIAS=30
TIPO_LOTE_CONSERVAR_ORIGINALES=false
```

Los controles de seguridad (`TIPO_AUTH_DISABLED`, `ALLOW_REMOTE_OLLAMA`, `ALLOW_NETWORK_EXPOSURE`, el sandbox de parsers, `INCLUIR_HASH_DOCUMENTO_AUDITORIA`, `PERMITIR_APAGADO_UI`, `TMPDIR`, la imagen de Ollama y su modo solo local) están fijados en `docker-compose.yml` y no se leen de `.env`. Cambiarlos exige editar ese fichero.

Los instaladores y el panel de Windows comprueban `.env` antes de usarlo: `PUERTO` debe ser un número, `PYTHON_IMAGE` solo admite `python:3.12-slim` (con o sin digest) y los nombres de modelo solo caracteres seguros. Si algo no cumple, se detienen con un mensaje.

### Conservación de lo que se sube

Desde `0.3.1-beta.1`, por defecto:

- Los documentos originales de un lote se borran en cuanto cada libro termina. Para conservarlos: `TIPO_LOTE_CONSERVAR_ORIGINALES=true`.
- Los lotes terminados o cancelados se borran a los **30 días** (`TIPO_LOTE_RETENCION_DIAS`; `0` = sin límite). Para un aula o un equipo compartido se recomienda `7`. La interfaz muestra el plazo en cada lote.
- El registro de eventos de seguridad se purga a los 90 días (`TIPO_EVENTOS_RETENCION_DIAS`).
- En **modo incógnito**, la respuesta y la exportación JSON no llevan los nombres ni las huellas SHA-256 de los ficheros (se muestran como `archivo_1`, `archivo_2`…). En un lote incógnito los originales se borran al terminar cada libro; el resultado se guarda hasta que caduque o se borre el lote.

Si actualiza desde una versión anterior y su `.env` tenía `TIPO_LOTE_RETENCION_DIAS=0` y `TIPO_LOTE_CONSERVAR_ORIGINALES=true` (los valores de `.env.example` hasta ahora), esos valores se siguen respetando: cámbielos a mano si quiere el nuevo comportamiento.

Desinstalar borra los datos de Tipo guardados en Docker (usuarios, lotes, documentos y resultados).

Variables opcionales para procesamiento por lotes:

```env
TIPO_MAX_LIBROS_LOTE=50
TIPO_MAX_BYTES_LOTE=2147483648
TIPO_LOTE_REINTENTOS_MAX=1
TIPO_LOTE_DIR=/app/data/batches
TIPO_LOTE_ZIP_MAX_ENTRADAS=60
TIPO_LOTE_ZIP_MAX_DESCOMPRIMIDO=209715200
TIPO_LOTE_ZIP_MAX_RATIO=100
```

La lista desplegable de modelos muestra los modelos ya descargados en Ollama. La imagen Docker de Ollama está fijada por versión en `docker-compose.yml` (no se lee de `.env`). Para fijarla además por digest se usa `scripts/actualizar_ollama.sh <versión>` (o `.ps1`), que comprueba la versión de la imagen y rechaza las anteriores a 0.35.0. En Windows, el instalador resuelve automáticamente la imagen base `python:3.12-slim` a digest y la guarda en `.env` antes de construir la imagen, sin intervención del usuario final.

---

## Compatibilidad

| Componente | Estado en `0.3.0-beta.1` |
| --- | --- |
| Ollama | Sin cambios. Compatible con `gemma4:e4b` y modelos equivalentes con visión. |
| Docker Compose | Sin cambios estructurales. El volumen `tipo-data` cubre `/app/data/batches`. |
| Esquemas | Sin cambios. `marc21-monografias` sigue siendo el perfil principal. |
| API existente | `/api/describir` y el resto de endpoints anteriores siguen funcionando. |
| Auditoría | Idéntica por libro; el lote no añade todavía eventos agregados propios en `security_events`. |

---

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

El proyecto incorpora medidas de higiene y revisión como `.dockerignore`, scripts de comprobación, auditoría de dependencias, generación de SBOM y política de actualización de dependencias.

---

## Verificación rápida tras instalar o actualizar

Una prueba básica de `0.3.0-beta.1` consiste en subir dos PDF en modo **Varios libros — uno por fichero**.

El comportamiento esperado es:

1. Tipo crea el lote mediante `POST /api/lote`.
2. La interfaz muestra un navegador con dos chips numerados.
3. Cada chip muestra el estado de su libro: pendiente, en curso, listo, error o cancelado.
4. Al terminar el primer libro, se renderiza automáticamente su propuesta revisable.
5. El segundo libro puede consultarse desde su chip correspondiente.
6. El selector de descarga de lote aparece cuando hay al menos un libro listo.
7. El ZIP descargado contiene una carpeta por libro y la colección agregada.

---

## Problemas conocidos

- El procesamiento real sigue siendo **secuencial en CPU**, condicionado por Ollama. Subir diez libros no hace que el proceso sea diez veces más rápido; hace que sea más cómodo y automatizado.
- Si Ollama supera el timeout configurado en `TIPO_TIMEOUT_LLM`, ese libro queda en estado `error` y el lote continúa con el siguiente.
- Todavía no hay reintento automático completo para errores transitorios de Ollama.
- La caché del navegador puede mantener cargada una versión anterior del frontend. Tras actualizar, conviene forzar recarga con **Ctrl + F5** o **Cmd + Shift + R**.
- La validación MARC21 es estructural. La prueba funcional en SIGB reales debe realizarse antes de usar los registros en producción.

---

## Prompt técnico del modelo

El prompt usado para solicitar la extracción bibliográfica al modelo local puede revisarse en:

```text
docs/PROMPT_MODELO_TIPO.md
```

---

## Próximos pasos previstos

- `0.3.x`: reintentos automáticos para errores transitorios de Ollama.
- `0.3.x`: eventos `lote_inicio` y `lote_fin` en `security_events`.
- `0.3.x`: tests adicionales del worker de lotes, incluyendo cancelación durante un ítem, reentrada tras interrupción y consistencia de agregados.
- `0.4.x`: perfiles adicionales, como publicaciones seriadas y recursos electrónicos.
- `0.4.x`: exploración de exportación o integración mediante Z39.50 / SRU.

---

## Autoría y licencia

Autoría y desarrollo conceptual: **Víctor Villapalos Pardiñas**.

Tipo se distribuye bajo la **GNU Affero General Public License v3 o posterior** (AGPL-3.0-or-later). Ver [`LICENSE`](LICENSE).

Copyright (C) 2026 Víctor Villapalos Pardiñas.

