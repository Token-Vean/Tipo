# Procesamiento por lotes — primera entrega backend

Esta entrega añade procesamiento desatendido de múltiples monografías sobre
el pipeline existente de Tipo. Reutiliza la validación, sandbox, segmentación
por zonas, extractor LLM y validaciones bibliográficas tal cual están.

## Ficheros nuevos

| Fichero                                  | Qué hace                                              |
| ---------------------------------------- | ----------------------------------------------------- |
| `backend/app/lotes.py`                   | Modelo de datos en SQLite, persistencia, worker único asyncio, reentrancia, cancelación. |
| `backend/app/lotes_api.py`               | Router HTTP `/api/lote*`. Hereda CSRF / auth / acceso local. |
| `backend/app/exportadores_lote.py`       | Exportación de colección (MARCXML `<collection>`, MARC-TXT, ISBD, JSON, CSV, ZIP). No toca `exportadores.py`. |

## Ficheros modificados

| Fichero                                  | Cambio                                                |
| ---------------------------------------- | ----------------------------------------------------- |
| `backend/app/main.py`                    | Registra `lotes_api.router`, llama a `recuperar_arranque()` y arranca el worker en `lifespan`. Aplicar `main.py.diff`. |
| `.env.example`                           | Añade variables `TIPO_MAX_LIBROS_LOTE`, `TIPO_MAX_BYTES_LOTE`, etc. Ver `env.example.lote.txt`. |

## Modelo conceptual

- **Lote** (`/api/lote`): un trabajo creado por un usuario. Estado:
  `pendiente | en_proceso | finalizado | cancelado`.
- **Item**: un libro dentro del lote. Estado:
  `pendiente | en_proceso | listo | error | cancelado`.
- **Worker**: un único `asyncio.Task` que vive con el proceso. Toma items de la
  cola y los procesa en serie. Comparte `_SEM_PROCESAMIENTO` con `/api/describir`,
  así que un libro suelto y un lote no compiten por Ollama: se serializan.

## Persistencia

- SQLite: mismo fichero que auth (`/app/data/tipo_auth.sqlite3`), dos tablas
  nuevas (`lotes`, `lote_items`). Esquema en `lotes._ensure_schema`.
- Disco: ficheros de entrada y `result.json` en `/app/data/batches/<lote_id>/<item_id>/`.
- Volumen `tipo-data` ya está montado RW sobre un contenedor `read_only:true`,
  así que no hace falta tocar `docker-compose.yml`.

## Endpoints

| Método | Ruta                                       | Qué hace                                          |
| ------ | ------------------------------------------ | ------------------------------------------------- |
| POST   | `/api/lote`                                | Crea un lote a partir de múltiples ficheros multipart. |
| GET    | `/api/lote`                                | Lista lotes del usuario actual.                   |
| GET    | `/api/lote/{lote_id}`                      | Estado del lote y de todos sus items.             |
| GET    | `/api/lote/{lote_id}/item/{item_id}`       | Resultado completo de un item (mismo shape que `/api/describir`). |
| POST   | `/api/lote/{lote_id}/cancelar`             | Marca pendientes como cancelados. No interrumpe el actual. |
| DELETE | `/api/lote/{lote_id}`                      | Borra registros y ficheros del lote. Requiere lote terminado/cancelado. |
| GET    | `/api/lote/{lote_id}/exportar/{formato}`   | Exporta el lote completo. Formatos: `json`, `csv`, `isbd`, `marcxml`, `marc-txt`, `zip`. |

## Modos de agrupación al subir

- `un_libro_por_fichero` (defecto): cada UploadFile = 1 libro. Caso típico:
  carpeta de PDFs completos, uno por monografía.
- `un_libro_por_zip`: cada UploadFile (debe ser .zip) = 1 libro con varios
  ficheros dentro (imágenes de cubierta, portadilla, colofón, etc.). Validación
  anti-zipbomb separada de la del DOCX.

## Prueba con curl

Asumiendo Tipo arrancado en `http://localhost:8082`, usuario `admin` autenticado.
Hay que mantener cookie de sesión y CSRF token. Atajo: hacer login con `curl -c`
guardando cookies, luego pedir `/api/csrf` y usar el token en cabecera.

```bash
# 1. Login (guarda cookie de sesión)
curl -s -c cookies.txt -b cookies.txt -H 'Content-Type: application/json' \
     -X POST http://localhost:8082/api/auth/login \
     -d '{"username":"admin","password":"TU_PASSWORD"}' | jq .

# 2. Pedir CSRF token
CSRF=$(curl -s -b cookies.txt -c cookies.txt http://localhost:8082/api/csrf | jq -r .token)

# 3. Crear lote (3 libros como PDF; agrupacion "un_libro_por_fichero" por defecto)
curl -s -b cookies.txt -c cookies.txt \
     -H "X-CSRF-Token: $CSRF" \
     -X POST http://localhost:8082/api/lote \
     -F 'ficheros=@libro1.pdf' \
     -F 'ficheros=@libro2.pdf' \
     -F 'ficheros=@libro3.pdf' \
     -F 'norma=marc21-monografias' \
     -F 'modo=esencial' \
     -F 'idioma_salida=es' \
     -F 'modelo=gemma4:e4b' | jq .
# → {"lote_id":"abc123...","estado_inicial":"pendiente",...}

# 4. Pollear estado
LOTE=abc123...
curl -s -b cookies.txt http://localhost:8082/api/lote/$LOTE | jq '.lote, .items[] | {id, orden, estado}'

# 5. Resultado individual
curl -s -b cookies.txt http://localhost:8082/api/lote/$LOTE/item/<item_id> | jq .

# 6. Exportar lote completo en MARCXML como colección
curl -s -b cookies.txt -O -J http://localhost:8082/api/lote/$LOTE/exportar/marcxml

# 7. Exportar como ZIP con todos los formatos por libro + colección
curl -s -b cookies.txt -O -J http://localhost:8082/api/lote/$LOTE/exportar/zip

# 8. Cancelar pendientes (no interrumpe item en curso)
curl -s -b cookies.txt -H "X-CSRF-Token: $CSRF" \
     -X POST http://localhost:8082/api/lote/$LOTE/cancelar | jq .
```

Para el modo ZIP por libro:

```bash
curl -s -b cookies.txt -c cookies.txt \
     -H "X-CSRF-Token: $CSRF" \
     -X POST http://localhost:8082/api/lote \
     -F 'agrupacion=un_libro_por_zip' \
     -F 'ficheros=@libro1.zip' \
     -F 'ficheros=@libro2.zip' \
     -F 'norma=marc21-monografias' \
     -F 'modo=esencial' \
     -F 'idioma_salida=es' \
     -F 'modelo=gemma4:e4b'
```

## Lo que NO incluye esta entrega

- Frontend. La vista en `app.js`/`index.html` queda para una segunda vuelta una
  vez validemos la API.
- Reanudación automática tras error: un item en `error` se queda así; hay que
  recrear el lote. Si quieres reintentos automáticos de errores transitorios
  (timeout de Ollama, fallo de red), lo añadimos como flag opcional.
- Notificación push al frontend. El cliente debe pollear `/api/lote/{id}` con
  el cadencia que prefiera. Si quieres, podemos cambiar a SSE.

## Notas operativas

- `MAX_PROCESAMIENTOS_SIMULTANEOS=1` en api.py se respeta tal cual. No cambia
  nada del comportamiento existente.
- `router.procesar()` se llama vía `asyncio.to_thread()` desde el worker para
  no bloquear el event loop durante la fase de parsing/zonas (Ollama ya es async
  por httpx). Esto mejora la responsividad mientras hay lote en curso.
- Los `result.json` de cada item quedan en disco hasta que el usuario borre el
  lote. Si quieres TTL automático, añade un job de limpieza.
- Auditoría por libro es idéntica a la actual (ficha técnica completa con hash,
  cobertura de zonas, evidencias). El lote en sí no genera entradas extra en
  `security_events`: si quieres ese registro adicional, dímelo y lo añado.
