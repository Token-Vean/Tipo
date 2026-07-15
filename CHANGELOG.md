# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Tipo sigue [versionado semántico](https://semver.org/lang/es/) en su variante beta.

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
