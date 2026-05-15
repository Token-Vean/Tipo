# Tipo v0.2.0-beta.6 — paquete de mejoras

Mejoras de robustez, precisión y usabilidad sobre la v0.2.0-beta.6. Todos los
ficheros van en su ruta correspondiente del repositorio de Tipo, respetando
la estructura original.

## Qué cambia

### Núcleo (backend)

1. **Segmentación por zonas** (`backend/app/zonas.py`, nuevo). Se sube el libro
   completo. Tipo localiza por sí mismo las zonas con datos descriptivos
   —preliminares (cubierta, portada, verso) y finales (colofón, depósito
   legal)— y descarta el cuerpo. Cada página enviada al modelo lleva una
   cabecera citable (`===== preliminares · página 3 de 210 =====`) para que el
   modelo pueda indicar la zona de cada evidencia.

2. **Modelo `gemma4:e4b`** (`Modelfile`, `.env.example`, `bootstrap.py`).
   Multimodal, *system prompt* nativo, ventana de 128K, buen rendimiento OCR.

3. **Prompt por áreas ISBD** (`backend/app/extractor.py`). El método de
   trabajo está reorganizado siguiendo el procedimiento real de un
   catalogador: recorrer las áreas ISBD en orden (0, 1, 2, 4, 5, 6, 7, 8) y,
   dentro de cada una, cuatro fases internas: evidencias literales → decisión
   descriptiva → revisión crítica → ensamblaje ISBD. Incluye jerarquía de
   fuentes ISBD, puntuación literal por área y reglas críticas de
   desambiguación: `(eds.)` como mención de responsabilidad no como edición,
   ilustrador de cubierta nunca como nota, fecha solo en D.L. transcrita
   como "D.L. AÑO", varias obras del mismo autor con ` ; `, "Anónimo"
   admitido, "reimpresión" ≠ "edición".

4. **Doble salida: campos atómicos + bloques ISBD por área**
   (`schemas/datos-bibliograficos-monografia.yaml`, sección `bloques_isbd`).
   El modelo devuelve en paralelo los campos atómicos (que se proyectan a
   MARC21) y los bloques ISBD ensamblados con su puntuación
   (`isbd_area_0..8`) para revisión humana directa. Si el modelo no devuelve
   un bloque, `bibliografico.py` lo reconstruye determinista a partir de los
   campos atómicos. Si difieren, se añade una advertencia.

5. **Vista MARC21 etiquetada** (`backend/app/exportadores.py`). Nueva función
   `generar_marc21_texto()` que produce el registro MARC21 línea a línea con
   etiqueta, indicadores (con `#` para blanco) y subcampos `$a $b $c`. La
   respuesta de `/api/describir` ahora incluye `marc21_lineas` (estructurado)
   y `marc21_texto` (texto plano). Nuevo formato de exportación `marc-txt`
   para volcar el registro a `.txt` listo para pegar en un OPAC.

6. **Modo incógnito** (`api.py`, `auditoria.py`). El frontend puede activar
   un toggle que añade `incognito=1` al formulario. En ese modo:
   - El log de la petición solo registra el evento, sin detalles.
   - La ficha técnica devuelta solo lleva `modo_incognito: true` y la
     configuración mínima del procesamiento (sin nombre de archivo, sin
     hashes, sin contadores que puedan reidentificar el material).
   Pensado para procesar material con datos personales o donaciones aún no
   públicas sin dejar rastro detallado.

7. **Ejemplos few-shot** (`schemas/ejemplos-monografia.yaml`). Diez casos
   redactados a mano cubriendo dificultades reales: fecha solo en D.L.,
   `(eds.)` como responsabilidad, varias obras del mismo autor, traducción
   con varios traductores, obra anónima, serie con número, series anidadas,
   actas de congreso con editor institucional, edición numerada, mención de
   coordinación tratada como responsabilidad. Cada salida incluye los
   campos atómicos y los bloques ISBD por área. `MAX_EJEMPLOS_PROMPT=3` por
   defecto; el resto sirve para evaluación posterior.

8. **Esquema ampliado** (`schemas/datos-bibliograficos-monografia.yaml`).
   Campos nuevos: depósito legal (017$a), lengua original (041$h), título
   original (240$a). Cada elemento tiene `ejemplo` y `error_comun`. Sección
   completa `bloques_isbd` con los 8 elementos ISBD por área.

9. **Robustez de respuesta del modelo** (`extractor.py`). Lectura tolerante
   de JSON (fences markdown, ruido, llaves anidadas, comillas internas),
   detección de truncamiento y reintento automático.

10. **Cobertura de zonas en auditoría y respuesta** (`api.py`, `auditoria.py`).
    Ficha técnica y respuesta registran qué se analizó realmente, sin
    incluir texto bibliográfico.

### Frontend

11. **Visualización profesional** (`frontend/static/styles.css`). Paleta de
    catálogo (papel y rojo brand), tipografía cuidada (Inter de cuerpo,
    serif tipo Iowan / Georgia para los bloques ISBD), sombras suaves,
    radios consistentes, transiciones cortas. Layout responsive.

12. **Modo claro / oscuro y densidad de fuente**. Botones en la barra
    superior (☼ / A). Tres densidades: compacto, cómodo, holgado.
    Persistencia en `localStorage`.

13. **Pestaña MARC21 nueva** que muestra el registro etiquetado en
    monoespaciado, con cada `$subcampo` resaltado y un botón ⧉ por línea
    para copiar al portapapeles. Botón global "Copiar todo MARC21".

14. **Vista ISBD por áreas con ficha completa al final** (`tab-isbd`). Cada
    bloque ISBD (Áreas 0, 1, 2, 4, 5, 6, 7, 8) se muestra como tarjeta con
    su zona, confianza y un botón de copia individual. Al final, una
    **ficha completa concatenada** en formato libro (serif), tal y como
    saldría en un catálogo, con su propio botón "Copiar ficha".

15. **Semáforo de confianza**. Cada campo y cada bloque ISBD lleva un borde
    izquierdo de 4 px coloreado: verde (alta), ámbar (media), rojo (baja),
    gris (sin valor). Las insignias del lado derecho replican el código.

16. **Copia granular**. Botón ⧉ en cada campo atómico, cada bloque ISBD y
    cada línea MARC21. Botones globales "Copiar todo ISBD" y "Copiar todo
    MARC21". Feedback visual breve ("✓ Copiado") al pulsar.

17. **Plantillas institucionales** (panel desplegable bajo el formulario).
    Editor, lugar de publicación, prefijo D.L. y serie habitual se
    recuerdan en `localStorage` y se aplican como fallback en los campos
    que el modelo deja vacíos, marcándolos con confianza "baja" y la
    advertencia correspondiente.

18. **Botones flotantes** en la esquina inferior derecha:
    - ℹ **Instrucciones**: modal con 8 pasos del flujo y lo que Tipo no
      hace.
    - 📜 **Normativa**: modal con las áreas ISBD cubiertas, la jerarquía de
      fuentes, la proyección a MARC21 y el alcance de la herramienta.
    - ⌨ **Atajos de teclado**: modal con la lista.
    - ⊞ **Modo flotante**: abre Tipo en una ventana lateral compacta.

19. **Modo flotante (ventana lateral)**. Pulsando el FAB ⊞ o `Ctrl+K`, Tipo
    abre una segunda ventana (520 × 900) con la URL `?modo=flotante`. Esta
    activa una hoja de estilo compacta (una columna, hero reducido, FABs
    más pequeños) pensada para trabajar al lado de otro software (OPAC,
    Athento, AtoM…). La app es además **instalable como PWA** mediante el
    `manifest.json`; en navegadores compatibles eso permite "always on
    top" via Chrome → Más herramientas → Crear acceso directo.

20. **Atajos de teclado**: `Ctrl+Enter` procesar, `Esc` cerrar modales,
    `F1` instrucciones, `F2` normativa, `Ctrl+K` ventana flotante,
    `Ctrl+Shift+D` alternar tema.

21. **CSP estricto** (ya presente en `api.py`): `default-src 'self';
    script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'
    data:; font-src 'self'; object-src 'none'; connect-src 'self';
    frame-ancestors 'none'; base-uri 'self'; form-action 'self'`. Cierra
    clases completas de ataques XSS antes de que existan.

22. **Sanitización en el frontend**. Los nombres de archivo mostrados se
    sanean (`sanearNombre`) antes de inyectarse en la lista de subidas,
    en cobertura y en los nombres de descarga.

## Cómo se integran los ejemplos

Sin red en tiempo de ejecución.

1. `schemas/ejemplos-monografia.yaml` viaja DENTRO de la imagen, en
   `/app/schemas/`. El extractor lo lee al construir el prompt (variable
   `RUTA_EJEMPLOS`, `MAX_EJEMPLOS_PROMPT=3` por defecto). Si el fichero no
   existe, Tipo funciona igual sin few-shot.
2. Los 10 ejemplos están redactados a mano siguiendo convenciones ISBD y
   MARC21. Cada uno trae el material simulado en una zona realista (con
   cabeceras `===== preliminares · página 4 de 10 =====`) y la salida JSON
   exacta: campos atómicos + bloques ISBD por área con puntuación.
3. Para ampliar con MARCXML real de la BNE, usar
   `examples/construir_ejemplos_bne.py` en tiempo de construcción.
4. En producción Tipo NUNCA toca la red. Solo lee ese YAML del disco.

## Verificación

```
pytest backend/tests/test_zonas.py -q
```

Cubre la segmentación por zonas (descarte del cuerpo, no solapamiento, tope
de visión, cabeceras citables) y la lectura tolerante de JSON. No requiere
Ollama.

## Notas de integración

- El `manifest.json` añadido permite instalar Tipo como PWA. Si no quieres
  ese comportamiento, borra `frontend/static/manifest.json` y la línea
  `<link rel="manifest" href="/manifest.json" />` de `index.html`.
- El CSP servido por `api.py` es estricto pero permite `style-src
  'unsafe-inline'` por compatibilidad con un par de estilos inline del HTML
  (un `style="flex:1;margin:0"` en `app.js`); si lo quieres aún más
  cerrado, mueve esos estilos a `styles.css` y elimina `'unsafe-inline'`.
- El modo flotante depende de `window.open` con dimensiones. Si el
  navegador bloquea popups, el usuario debe permitirlos para este origen.
