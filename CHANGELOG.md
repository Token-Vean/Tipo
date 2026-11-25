# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Tipo sigue [versionado semántico](https://semver.org/lang/es/) en su variante beta.

## [0.3.1-beta.1] — pendiente de publicación

Release de **seguridad y privacidad** preparada para el curso de SEDIC.
Recoge todo lo hecho en `main` desde julio (que nunca llegó a publicarse) y
la revisión de noviembre de 2026. Recomendada para todas las instalaciones:
la 0.3.0-beta.2 publicada lleva Pillow 12.3.0 y pypdf 6.13.3, con avisos
críticos y altos.

### Seguridad (revisión de noviembre de 2026)

- **Recuperar el administrador desde el panel de Windows no funcionaba.** La
  contraseña se escribía en un `.env` temporal y se pasaba con
  `docker compose run --env-file`, que solo sirve para interpolar el fichero
  de Compose: la variable no llegaba al contenedor. Ahora viaja solo en el
  entorno del proceso (`-e TIPO_RECOVERY_PASSWORD`), sin tocar el disco. El
  panel valida el nombre de usuario con el mismo patrón que el backend antes
  de montar la orden de `cmd.exe`, comprueba el código de salida de cada paso
  y lee stdout y stderr en paralelo (con `docker compose build` el panel podía
  quedarse colgado con el búfer de stderr lleno).
- **Validación de `.env` antes de usarlo** (`tools/windows/validar-env.ps1`,
  `validar_env` en `instalar.sh`): `PUERTO` se insertaba en órdenes de
  PowerShell y un valor con comillas ejecutaba código; `PYTHON_IMAGE` podía
  cambiar la imagen base del contenedor que procesa los documentos. Ahora
  `PUERTO` debe ser un número entre 1024 y 65535, `PYTHON_IMAGE` solo admite
  `python:3.12-slim` (con o sin digest), y `MODELO_*` y `PERFIL` se validan.
- **Linux: Ollama dentro de Docker por defecto.** El perfil `external` no
  conectaba con el Ollama del equipo (escucha en `127.0.0.1` y el contenedor
  llega por el puente de Docker), y el remedio habitual,
  `OLLAMA_HOST=0.0.0.0`, abre Ollama a toda la red local. El instalador usa
  `bundled` salvo `TIPO_PERFIL=external`, y el README explica cómo hacerlo
  sin exponer Ollama.
- **Apagar Tipo desde la interfaz exige ser administrador.** Un usuario normal
  podía detener el servicio para todos. El botón se oculta a quien no lo es.
- **Delimitadores del prompt neutralizados** (`app/delimitadores.py`, como en
  PlumA 0.7.2). El texto del documento, los nombres de archivo y las etiquetas
  ya no pueden contener `<<<DOCUMENTO_FIN>>>` ni imitar las cabeceras de zona
  y página (`#####`, `=====`) o de fuente (`### Fuente:`).
- **`INCLUIR_HASH_DOCUMENTO_AUDITORIA` y `PERMITIR_APAGADO_UI`** pasan a ser
  literales en `docker-compose.yml`, como el resto de controles.
- **`MODELO_BASE` y `MODELO_NOMBRE`** se validan antes de `/api/pull`: no se
  admiten registros de modelos distintos del de Ollama y de Hugging Face.
- **Ollama en Docker en modo solo local** (`OLLAMA_NO_CLOUD=1`).
  `scripts/actualizar_ollama.sh` / `.ps1` fijan el digest de una versión
  concreta, comprueban la versión que informa la imagen y rechazan 0.34.2–0.34.x
  (CVE-2026-103663, path traversal en `/api/pull`).
- **Sesiones:** tope absoluto de 7 días (`TIPO_SESSION_MAX_SECONDS`) a la
  renovación deslizante, y un inicio de sesión nuevo revoca el token anterior
  de ese navegador.
- **lxml** 6.1.0 → **6.1.1** (CVE-2026-49825, en `Cleaner`, que Tipo no usa;
  se sube para que `pip-audit --strict` no bloquee el CI).

### Privacidad (revisión de noviembre de 2026)

- **Conservación limitada por defecto.** Los lotes terminados se borran a los
  30 días (antes `.env.example` los conservaba sin límite) y los documentos
  originales se borran en cuanto cada libro termina
  (`TIPO_LOTE_CONSERVAR_ORIGINALES=false`). La retención se aplica también
  cada 6 horas mientras el worker está en reposo, no solo al arrancar o al
  crear un lote. La interfaz muestra el plazo en cada lote.
- **Modo incógnito completo.** No se calcula la huella SHA-256 y la respuesta
  (y con ella la exportación JSON) sustituye los nombres de archivo por
  `archivo_1`, `archivo_2`…; también en el `result.json` de los lotes
  incógnito. El nombre del fichero ya no aparece en el log cuando falla su
  validación en incógnito.
- **Eventos de seguridad con retención** de 90 días
  (`TIPO_EVENTOS_RETENCION_DIAS`).
- El desinstalador y el panel avisan de que se borran los usuarios, lotes,
  documentos y resultados.

### Corregido

- Las subidas de lotes se escribían en `/tmp`, un tmpfs de 512 MB en RAM que
  cuenta contra el límite de memoria del contenedor: un lote de más de unos
  500 MB fallaba y uno menor podía llevar el contenedor al límite de memoria.
  Ahora van a `/app/data/tmp`, en el volumen, que se vacía al arrancar.
- El panel de Windows tomaba 8082 (el puerto de PlumA) como puerto por defecto
  y podía dar por arrancado Tipo cuando respondía PlumA. Ahora usa 8769 y
  comprueba que quien responde es Tipo (`/api/estado` incluye `aplicacion`).
- Las conexiones SQLite se cierran siempre al terminar cada operación (el
  gestor de contexto de `sqlite3` solo hacía commit o rollback).
- Un ZIP cifrado o con un método de compresión no admitido en un lote
  devuelve un error claro en lugar de un error 500.
- `auth_cli reset-admin` purga lotes huérfanos al crear un usuario nuevo, como
  ya hacía la API.
- `instalar.sh` escribe el log de construcción en un temporal propio
  (`mktemp`) en lugar de `/tmp/build.log`.
- El panel de Windows se guarda en UTF-8 con BOM: Windows PowerShell 5.1
  mostraba mal las tildes y la «ñ».
- CI: se retira el permiso `security-events: write`, que no se usaba, y se
  añade una prueba con el sandbox de parsers activado.

### Seguridad (noviembre de 2026, ya en `main`)

- Bloqueo de modelos remotos de Ollama por metadatos (`remote_host`,
  `remote_model`), no solo por la etiqueta `:cloud`, antes de cada inferencia y
  en el arranque.
- Cliente HTTP único hacia Ollama con `trust_env=False` y sin redirecciones.
- `CabecerasSeguridad` como middleware más externo; PBKDF2 (600 000
  iteraciones) siempre fuera del bucle de eventos.
- Puerto 8769 por defecto, para poder usar Tipo y PlumA a la vez.
- **pypdf** → **6.21.4**.

### Seguridad (octubre de 2026, ya en `main`)

- **Pillow** 12.3.0 → **13.0.0**: 4 avisos críticos y 23 altos (desbordamientos
  de heap en los decodificadores TIFF y JPEG y en FreeType, inyección de
  argumentos en la llamada a Ghostscript, lecturas fuera de límites). Tipo
  decodifica imágenes y PDF aportados por el usuario. Pillow 13 exige Python
  3.11 o superior; la imagen Docker ya usa 3.12 y `requires-python` ya era
  `>=3.11`.
- **pypdf** 6.19.0 → **6.21.2**: 7 avisos moderados y 1 bajo de denegación de
  servicio por PDF manipulado.
- **certifi** 2026.4.22 → **2026.10.19**: retira las raíces emSign cuyas CA
  intermedias quedaron comprometidas.
- **Controles de seguridad fijados en `docker-compose.yml`.** La imagen de
  Ollama (`OLLAMA_IMAGE`), el sandbox de parsers (`USAR_SANDBOX_PARSERS`,
  `SANDBOX_TIMEOUT_SEGUNDOS`, `SANDBOX_MEMORIA_MB`), `ALLOW_REMOTE_OLLAMA`,
  `ALLOW_NETWORK_EXPOSURE` y `TIPO_AUTH_DISABLED` se leían de `.env`: un `.env`
  manipulado o heredado podía sustituir el contenedor que recibe el texto de
  los documentos, desactivar el aislamiento de los parsers o el inicio de
  sesión sin aviso. Pasan a ser literales en ambos servicios (`app` y
  `app-external`), igual que en PlumA, y desaparecen de `.env.example`.
  `tests/test_configuracion_bloqueada.py` impide que vuelvan a ser variables.

### Licencia

- `LICENSE` y `frontend/static/LICENSE.txt` no contenían el texto íntegro de la
  AGPL-3.0: solo el aviso abreviado y una nota de «paso pendiente antes de
  publicar». Además, el titular figuraba como «Víctor Villapalos Sánchez». Ahora
  `LICENSE` lleva el texto íntegro y `LICENSE.txt` (el que enlaza la interfaz)
  añade el aviso de copyright correcto, Víctor Villapalos Pardiñas, y el enlace
  al código fuente.

### Cambiado

- Versión unificada en 0.3.1-beta.1 en `VERSION`, `app/version.py`,
  `pyproject.toml` (antes desalineados entre 0.2.0-beta.7, 0.3.0-beta.1 y
  0.3.0b2), el instalador, el panel de Windows, `.env.example` y
  `scripts/crear_release_windows.ps1`.
- Se retira `README_Tipo_actualizado_v0.3.0-beta.1.md`, una copia antigua del
  README que aún describía los controles de seguridad como variables de `.env`.

### Notas para la actualización

- Si su `.env` define alguna de las variables que ahora están fijadas en
  `docker-compose.yml`, ya no tiene efecto. Para cambiarlas hay que editar ese
  fichero.
- Si su `.env` viene de una versión anterior, puede tener
  `TIPO_LOTE_RETENCION_DIAS=0` y `TIPO_LOTE_CONSERVAR_ORIGINALES=true`. El
  instalador no los cambia, para no borrar datos sin su consentimiento:
  edítelos a mano si quiere el nuevo comportamiento.
- Antes de publicar: fijar la versión de Ollama con
  `scripts/actualizar_ollama.sh <versión>` (el digest actual es de mayo de
  2026) y anotarla aquí.

## [0.3.0-beta.2] — 2026-07-15

Release de **seguridad**. No cambia funcionalidad ni interfaz: corrige una
vulnerabilidad de dependencia y actualiza el proceso para que este tipo de
hallazgos deje de pasar inadvertido. Recomendada para todas las instalaciones.

### Seguridad

- **BadHost / CVE-2026-48710 (GHSA-86qp-5c8j-p5mr).** Starlette 1.0.0
  reconstruía `request.url` a partir de la cabecera `Host` sin validarla, de
  modo que la ruta vista por un middleware podía divergir de la que el router
  despachaba realmente. Doble mitigación:
  - Los middlewares de seguridad (`auth.py`, `csrf.py`, `local_access.py`,
    `api.py`) pasan a decidir sobre la ruta ASGI cruda `request.scope["path"]`
    en lugar de `request.url.path`. Este es el arreglo permanente: protege
    aunque una dependencia vuelva a introducir el fallo en el futuro.
  - `starlette` 1.0.0 → **1.3.1** (cierra también PYSEC-2026-248/249/2280/2281);
    `fastapi` 0.136.0 → **0.139.0**, última estable y probada contra
    Starlette 1.3.x, lo que garantiza compatibilidad de runtime.
- **python-multipart** 0.0.26 → **0.0.31**: PYSEC-2026-3036/3037/3039/3040
  (parseo de formularios multipart).
- **pypdf** 6.10.2 → **6.13.3**: denegación de servicio por PDF manipulado
  (GHSA-jm82-fx9c-mx94 y anteriores). El sandbox de parsers ya contenía el
  impacto (timeout + `RLIMIT_AS`), pero se actualiza igualmente.
- **Pillow** 12.2.0 → **12.3.0**: CVE-2026-55379 (asignación de memoria en
  fuentes BDF) y CVE-2026-55798 (`ImageShow`, no usado por Tipo).
- **idna** 3.13 → **3.15**: PYSEC-2026-215.

### Cambiado

- CI: `pip-audit` pasa a ser **bloqueante** para vulnerabilidades con
  corrección disponible (`--strict`), no solo informativo. Las excepciones
  puntuales se declaran con `--ignore-vuln` y justificación en el propio
  workflow. Esto cierra el hueco por el que la vulnerabilidad de Starlette
  había quedado únicamente en el informe.
- Vigilancia automática de dependencias mediante Dependabot
  (`.github/dependabot.yml`): actualizaciones semanales de pip, Docker y
  GitHub Actions.
- `requirements.txt`: eliminado un bloque de dependencias duplicado y una
  línea espuria heredados de una generación anterior del fichero.

### Notas para la actualización

- Reconstruir la imagen (`docker compose build`) para instalar las versiones
  nuevas.
- Sin cambios de configuración, de esquema de datos ni de puertos. No requiere
  migración.

---

## [0.3.0-beta.1] — 2026-05-18

Esta es la **release de tratamiento por lotes**. Tipo deja de catalogar
solo libro a libro y pasa a aceptar colecciones completas, manteniendo la
filosofía local-first y la trazabilidad por documento. La calidad de la
exportación MARC21 sube además a "importable en SIGB con revisión mínima".

### Añadido

#### Procesamiento por lotes

- Nuevo módulo `app/lotes.py`: cola FIFO de un único worker `asyncio` que
  consume items en serie. Comparte el semáforo global `_SEM_PROCESAMIENTOS`
  con `/api/describir`, por lo que un libro suelto y un lote en marcha se
  serializan correctamente contra Ollama sin pisarse.
- Nuevo módulo `app/lotes_api.py`: endpoints HTTP del lote, montados bajo
  el mismo `prefix="/api"` y heredando `ProteccionAccesoLocal`,
  `ProteccionAutenticacion`, `ProteccionCSRF` y `LimiteCuerpoPeticion`.
  - `POST   /api/lote` — crear lote (subida multipart, varios libros).
  - `GET    /api/lote` — listar lotes del usuario actual.
  - `GET    /api/lote/{id}` — estado agregado del lote y de cada item.
  - `GET    /api/lote/{id}/item/{item_id}` — payload completo del libro,
    con el mismo `shape` que `/api/describir`.
  - `POST   /api/lote/{id}/cancelar` — cancelación lógica. Pendientes →
    `cancelado`; el item en curso termina. Nunca se interrumpe a la mitad.
  - `DELETE /api/lote/{id}` — borra registros y ficheros. Solo válido en
    lotes ya terminados o cancelados.
  - `GET    /api/lote/{id}/exportar/{formato}` — descarga agregada.
- Dos modos de agrupación al subir:
  - **`un_libro_por_fichero`** (por defecto): cada `UploadFile` = 1 libro.
  - **`un_libro_por_zip`**: cada `UploadFile` (debe ser `.zip`) = 1 libro
    con varias imágenes/PDFs dentro. Validaciones anti-zipbomb propias
    (`TIPO_LOTE_ZIP_MAX_ENTRADAS`, `TIPO_LOTE_ZIP_MAX_DESCOMPRIMIDO`,
    `TIPO_LOTE_ZIP_MAX_RATIO`).
- Persistencia:
  - Tablas nuevas `lotes` y `lote_items` en el mismo SQLite que la auth
    (`/app/data/tipo_auth.sqlite3`), con WAL y `foreign_keys=ON`.
  - Ficheros de entrada y `result.json` por item en
    `/app/data/batches/<lote_id>/<item_id>/`. Compatible con el contenedor
    `read_only:true` actual: solo `tipo-data` es escribible.
- **Reentrancia**: al arrancar el servicio, los items que estuvieran en
  estado `en_proceso` por una caída pasan automáticamente a `pendiente`
  (con `intentos += 1`), o a `error` si superan `TIPO_LOTE_REINTENTOS_MAX`.
  La cola se reconstruye y el lote sigue donde lo dejó.
- **Auditoría por item idéntica a la actual**: `auditoria.generar_ficha_tecnica`
  produce la misma ficha técnica completa que `/api/describir` (hash,
  cobertura de zonas, evidencias, modo incógnito), una por libro.
- Nuevo módulo `app/exportadores_lote.py`: variantes de colección sin
  duplicar lógica con `exportadores.py`.
  - `marcxml` — un único `<collection>` con N `<record>`.
  - `marc-txt` — bloques `### Registro N: título` con MARC21 etiquetado.
  - `isbd` — bloques separados con la ficha ISBD concatenada por libro.
  - `json` — array con todos los payloads.
  - `csv` — una fila por libro, columnas estables (unión de claves).
  - `zip` — un fichero por libro en cada formato individual más una
    carpeta `coleccion/` con los formatos agregados y `manifiesto.json`.
- Frontend:
  - Selector "Modo de subida" en la sección de subida, con aviso
    contextual si el usuario sube varios ficheros con la opción
    "Un solo libro" seleccionada.
  - Navegador de lote sobre la propuesta revisable: chips numerados con
    color por estado (gris pendiente, ámbar pulsante en proceso, verde
    listo, rojo error, gris tachado cancelado), flechas anterior/siguiente,
    contador "Libro N de Total", agregados (`listos`, `errores`, `estado`).
  - Navegación con flechas izq/dcha del teclado.
  - Caché por `item_id` (cambiar de libro ya cargado es instantáneo).
  - Polling cada 2,5 s mientras quede trabajo; se detiene solo al terminar.
  - Selector "Descargar lote…" en la propia barra del navegador con los
    seis formatos de colección.
  - Botón "Cancelar lote" visible solo mientras está en curso.
- Nuevas variables de entorno (todas opcionales, con defaults seguros):
  - `TIPO_MAX_LIBROS_LOTE` (50)
  - `TIPO_MAX_BYTES_LOTE` (2 GB)
  - `TIPO_LOTE_REINTENTOS_MAX` (1)
  - `TIPO_LOTE_DIR` (`/app/data/batches`)
  - `TIPO_LOTE_ZIP_MAX_ENTRADAS` (60)
  - `TIPO_LOTE_ZIP_MAX_DESCOMPRIMIDO` (200 MB)
  - `TIPO_LOTE_ZIP_MAX_RATIO` (100)

#### Calidad para importación en SIGB

- Emisión obligatoria del campo `008` (control field, longitud fija 40):
  fecha de catalogación, tipo de fecha, fecha 1 derivada del año detectado
  en `fecha_publicacion`, código de país inferido por idioma, idioma del
  recurso, fuente de catalogación. Sin él, Koha/Aleph/Symphony marcaban el
  registro como incompleto.
- Emisión obligatoria del campo `041`, derivado del idioma de salida del
  lote (Koha indexa facets a partir de 041, no de 008).
- `245 ind1=1` por defecto: el SIGB genera entrada secundaria automática
  por título. Como Tipo no produce 1xx, sin este cambio los registros no
  eran encontrables por título tras la importación.
- Limpieza de puntuación ISBD inicial en subcampos `$b`, `$c` (245),
  `$a` (490): la puntuación de visualización la añade el SIGB; meterla
  dentro del subcampo producía duplicaciones al renderizar.
- Normalización RDA de `250` cuando el patrón es claro: `1ª Edición` →
  `1ª ed.`, `Primera edición` → `1ª ed.`. En casos complejos (revisada,
  ampliada, bilingüe…) se preserva el original.
- `264 ind1=1` (publicación vigente) en lugar de `ind1=" "`.
- La pestaña MARC21 de la UI y el TXT exportado mantienen plena coherencia
  con el MARCXML.

### Cambiado

- `exportadores.py`: refactorización a una función pública
  `_construir_record_marcxml(campos, idioma_salida)` que actúa como fuente
  única de verdad y la usan tanto `_exportar_marcxml` (libro suelto) como
  `exportadores_lote._record_marcxml_desde_payload` (lote).
- `generar_marc21_texto(campos)` → `generar_marc21_texto(campos, idioma_salida=None)`.
  Compatible hacia atrás.
- `main.py`: el `lifespan` ahora llama a `lotes.recuperar_arranque()` y
  `lotes.iniciar_worker_si_inactivo()` al arrancar, y a
  `lotes.detener_worker()` al cerrar.

### Notas para la migración

- Sin migración de datos. Las tablas de lote se crean al primer arranque.
- Los antiguos `result.json` de libros descritos con `/api/describir`
  seguían siendo válidos y se siguen visualizando igual.
- Si se conservaban MARCXML exportados con v0.2.0-beta.7 conviene
  regenerarlos: la versión nueva añade `008` y `041` y limpia la
  puntuación de subcampos, lo cual eleva la compatibilidad con Koha,
  Aleph, Symphony y Absys NET.

### Seguridad

- Sin nuevas dependencias.
- Sin nuevos puertos.
- El worker no requiere cookie de sesión: el `username` del propietario se
  guarda en la tabla `lotes` y se comprueba en cada GET/DELETE/exportar.
- Subida vía `un_libro_por_zip` con triple validación anti-zipbomb
  (entradas, tamaño descomprimido total, ratio por entrada).

---

## [0.2.0-beta.7] — 2026-05

Versión anterior. Catalogación libro a libro mediante `/api/describir`,
autenticación local de usuarios, segmentación por zonas, exportadores
ISBD/JSON/CSV/MARC21 TXT/MARCXML, panel Windows de instalación y
recuperación local de administrador.
