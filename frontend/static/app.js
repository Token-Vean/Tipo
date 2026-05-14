let csrfToken = null;
let ultimoResultado = null;
let currentLang = 'es';

const I18N = {
  es: {
    languageLabel: 'Idioma',
    statusPreparing: 'Preparando motor local…',
    statusReady: 'Motor local listo',
    statusNoBackend: 'Sin conexión con el backend local',
    shutdown: 'Apagar',
    shuttingDown: 'Apagando…',
    shutdownStarted: 'Apagado iniciado. Puede cerrar esta pestaña en unos segundos.',
    shutdownError: 'No se pudo solicitar el apagado. Use el script 2_DETENER si el servicio sigue activo.',
    eyebrow: 'Asistente local de precatalogación',
    heroTitle: 'Extracción bibliográfica para monografías impresas',
    heroText: 'Suba el libro completo (PDF, imágenes o documento) y Tipo localizará por sí mismo las zonas donde se encuentran los datos descriptivos para proponer una descripción estructurada revisable. El procesamiento se realiza en local mediante Ollama.',
    notice: 'Tipo no consulta catálogos externos, no crea puntos de acceso autorizados, no asigna materias normalizadas y no modifica sistemas bibliotecarios.',
    sourcesTitle: '1. El libro',
    sourcesHelp: 'Suba el libro completo. No hace falta separar portada, verso o colofón: Tipo localiza internamente las zonas donde suele estar la información (preliminares y finales) y descarta el cuerpo. También puede subir imágenes sueltas de páginas concretas si lo prefiere.',
    modeLabel: 'Modo',
    modeEssential: 'Esencial',
    modeComplete: 'Completo',
    languageOutputNote: 'La propuesta se generará en el idioma seleccionado para la interfaz.',
    process: 'Procesar',
    processing: 'Procesando…',
    reviewable: 'Propuesta revisable',
    resultTitle: '2. Resultado',
    audit: 'Auditoría',
    tabFields: 'Campos',
    tabIsbd: 'Vista ISBD',
    tabWarnings: 'Avisos',
    tabCoverage: 'Cobertura',
    noFiles: 'Suba al menos un fichero del libro.',
    noIsbd: 'Sin datos suficientes para generar vista ISBD.',
    evidence: 'Evidencia',
    zone: 'Zona',
    noWarnings: 'Sin advertencias.',
    coverageTitle: 'Zonas analizadas',
    coverageIntro: 'Tipo no procesa el libro entero: analiza solo las zonas donde se concentran los datos descriptivos.',
    coveragePagesTotal: 'Páginas del documento',
    coveragePagesAnalyzed: 'Páginas analizadas',
    coveragePagesDiscarded: 'Páginas descartadas',
    coveragePreliminares: 'Preliminares',
    coverageFinales: 'Finales',
    coverageRoute: 'Ruta de procesamiento',
    coverageNone: 'No se registró segmentación por zonas (por ejemplo, una imagen suelta).'
  },
  en: {
    languageLabel: 'Language',
    statusPreparing: 'Preparing local engine…',
    statusReady: 'Local engine ready',
    statusNoBackend: 'No connection to the local backend',
    shutdown: 'Shut down',
    shuttingDown: 'Shutting down…',
    shutdownStarted: 'Shutdown started. You can close this tab in a few seconds.',
    shutdownError: 'Could not request shutdown. Use the 2_STOP script if the service is still active.',
    eyebrow: 'Local pre-cataloging assistant',
    heroTitle: 'Bibliographic extraction for printed monographs',
    heroText: 'Upload the whole book (PDF, images or document) and Tipo will locate the zones where descriptive data usually appears, proposing a structured, reviewable description. Processing runs locally with Ollama.',
    notice: 'Tipo does not query external catalogues, does not create authorized access points, does not assign controlled subjects, and does not modify library systems.',
    sourcesTitle: '1. The book',
    sourcesHelp: 'Upload the whole book. There is no need to separate title page, verso or colophon: Tipo internally locates the zones where the information usually is (front matter and end matter) and discards the body. You may also upload single images of specific pages if you prefer.',
    modeLabel: 'Mode',
    modeEssential: 'Essential',
    modeComplete: 'Complete',
    languageOutputNote: 'The proposal will be generated in the selected interface language.',
    process: 'Process',
    processing: 'Processing…',
    reviewable: 'Reviewable proposal',
    resultTitle: '2. Result',
    audit: 'Audit',
    tabFields: 'Fields',
    tabIsbd: 'ISBD view',
    tabWarnings: 'Warnings',
    tabCoverage: 'Coverage',
    noFiles: 'Upload at least one file of the book.',
    noIsbd: 'Not enough data to generate the ISBD view.',
    evidence: 'Evidence',
    zone: 'Zone',
    noWarnings: 'No warnings.',
    coverageTitle: 'Analyzed zones',
    coverageIntro: 'Tipo does not process the whole book: it analyzes only the zones where descriptive data is concentrated.',
    coveragePagesTotal: 'Document pages',
    coveragePagesAnalyzed: 'Analyzed pages',
    coveragePagesDiscarded: 'Discarded pages',
    coveragePreliminares: 'Front matter',
    coverageFinales: 'End matter',
    coverageRoute: 'Processing route',
    coverageNone: 'No zone segmentation was recorded (for example, a single image).'
  }
};

const FIELD_NAMES_EN = {
  isbn: 'ISBN',
  deposito_legal: 'Legal deposit',
  lengua_texto: 'Language of text of this edition',
  idioma_original: 'Original language of the work',
  titulo_principal: 'Title proper',
  subtitulo: 'Subtitle or other title information',
  mencion_responsabilidad: 'Transcribed statement of responsibility',
  titulo_original: 'Original title of the work',
  mencion_edicion: 'Edition statement',
  lugar_publicacion: 'Place of publication',
  editor: 'Publisher',
  fecha_publicacion: 'Publication date',
  fecha_copyright: 'Copyright date',
  extension: 'Extent',
  ilustraciones: 'Illustrations or other physical details',
  dimensiones: 'Dimensions',
  tipo_contenido: 'Content type',
  tipo_medio: 'Media type',
  tipo_soporte: 'Carrier type',
  serie_transcrita: 'Transcribed series statement',
  nota_general: 'General note',
  nota_bibliografia: 'Bibliography note',
  resumen: 'Summary or scope note',
  nota_lengua: 'Language note'
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const t = (key) => (I18N[currentLang] && I18N[currentLang][key]) || I18N.es[key] || key;

async function init() {
  currentLang = localStorage.getItem('tipo-ui-lang') || (((navigator.language || 'es').toLowerCase().startsWith('en')) ? 'en' : 'es');
  if (!['es', 'en'].includes(currentLang)) currentLang = 'es';
  $('#ui-lang').value = currentLang;
  $('#ui-lang').addEventListener('change', cambiarIdioma);
  aplicarIdioma();
  try {
    const r = await fetch('/api/csrf', { cache: 'no-store', credentials: 'same-origin' });
    csrfToken = (await r.json()).token;
  } catch (_) {}
  comprobarEstado();
  setInterval(comprobarEstado, 4000);
  $('#ficheros').addEventListener('change', renderListaFicheros);
  $('#procesar').addEventListener('click', procesar);
  $('#btn-apagar').addEventListener('click', apagar);
  $$('.tab').forEach(btn => btn.addEventListener('click', () => activarTab(btn.dataset.tab)));
  $$('[data-export]').forEach(btn => btn.addEventListener('click', () => exportar(btn.dataset.export)));
  $('#auditoria').addEventListener('click', descargarAuditoria);
}

function cambiarIdioma(ev) {
  currentLang = ev.target.value === 'en' ? 'en' : 'es';
  localStorage.setItem('tipo-ui-lang', currentLang);
  aplicarIdioma();
  if (ultimoResultado) renderResultado();
}

function aplicarIdioma() {
  document.documentElement.lang = currentLang;
  $$('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
}

async function comprobarEstado() {
  try {
    const r = await fetch('/api/estado', { cache: 'no-store', credentials: 'same-origin' });
    const data = await r.json();
    $('#estado').textContent = data.listo ? t('statusReady') : (data.mensaje || t('statusPreparing'));
  } catch (_) {
    $('#estado').textContent = t('statusNoBackend');
  }
}

// Lista de ficheros: solo informativa. Ya no se etiqueta cada fichero a mano;
// Tipo localiza internamente las zonas del libro.
function renderListaFicheros() {
  const files = Array.from($('#ficheros').files || []);
  const cont = $('#lista-ficheros');
  cont.innerHTML = '';
  files.forEach((file) => {
    const row = document.createElement('div');
    row.className = 'file-row';
    row.innerHTML = `<div><div class="file-name">${escapeHtml(file.name)}</div><div class="field-meta">${Math.round(file.size / 1024)} KB</div></div>`;
    cont.appendChild(row);
  });
}

async function procesar() {
  const files = Array.from($('#ficheros').files || []);
  if (!files.length) { alert(t('noFiles')); return; }
  $('#procesar').disabled = true;
  $('#procesar').textContent = t('processing');
  const fd = new FormData();
  files.forEach(f => fd.append('ficheros', f));
  // Ya no se envían etiquetas por fichero: el backend segmenta por zonas.
  fd.append('norma', 'marc21-monografias');
  fd.append('modo', $('#modo').value);
  fd.append('idioma_salida', currentLang);
  try {
    const r = await fetch('/api/describir', {
      method: 'POST',
      credentials: 'same-origin',
      referrerPolicy: 'same-origin',
      headers: { 'X-CSRF-Token': csrfToken || '' },
      body: fd
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Error de procesamiento');
    ultimoResultado = await r.json();
    renderResultado();
  } catch (e) {
    $('#resultados').classList.remove('hidden');
    $('#tab-campos').innerHTML = `<div class="error">${escapeHtml(e.message)}</div>`;
  } finally {
    $('#procesar').disabled = false;
    $('#procesar').textContent = t('process');
  }
}

function renderResultado() {
  $('#resultados').classList.remove('hidden');
  const campos = ultimoResultado.propuesta.campos || [];
  $('#tab-campos').innerHTML = campos.map((c, i) => `
    <div class="field">
      <div>
        <div class="field-name">${escapeHtml(nombreCampo(c))}</div>
        <div class="field-meta">${escapeHtml(c.id)} · ${escapeHtml(c.clave)}</div>
      </div>
      <div>
        <textarea data-idx="${i}">${escapeHtml(valorTexto(c.valor))}</textarea>
        <div class="field-meta">${escapeHtml(t('evidence'))}: ${escapeHtml(c.evidencia || '—')}</div>
        ${c.zona ? `<div class="field-meta">${escapeHtml(t('zone'))}: ${escapeHtml(c.zona)}</div>` : ''}
      </div>
      <div class="badge">${escapeHtml(c.confianza || 'sin valor')}<br>${escapeHtml(c.estado_evidencia || '')}</div>
    </div>`).join('');
  $$('#tab-campos textarea').forEach(tarea => tarea.addEventListener('input', actualizarCampo));
  $('#isbd-text').textContent = ultimoResultado.isbd || t('noIsbd');
  const avisos = ultimoResultado.propuesta.advertencias || [];
  $('#tab-avisos').innerHTML = avisos.length ? avisos.map(a => `<div class="warn">${escapeHtml(a)}</div>`).join('') : `<p class="muted">${escapeHtml(t('noWarnings'))}</p>`;
  renderCobertura();
  activarTab('campos');
}

function renderCobertura() {
  const cont = $('#tab-cobertura');
  const cobertura = (ultimoResultado.documento && ultimoResultado.documento.cobertura_zonas) || [];
  const conDatos = cobertura.filter(c => c && c.estrategia === 'zonas');
  if (!conDatos.length) {
    cont.innerHTML = `<p class="muted">${escapeHtml(t('coverageNone'))}</p>`;
    return;
  }
  let html = `<p class="muted small">${escapeHtml(t('coverageIntro'))}</p>`;
  conDatos.forEach(c => {
    const prelim = Array.isArray(c.preliminares) ? c.preliminares.join(', ') : '—';
    const finales = Array.isArray(c.finales) && c.finales.length ? c.finales.join(', ') : '—';
    html += `
      <div class="field">
        <div>
          <div class="field-name">${escapeHtml(c.archivo || c.etiqueta || '—')}</div>
          <div class="field-meta">${escapeHtml(t('coverageRoute'))}: ${escapeHtml(c.ruta || '—')}</div>
        </div>
        <div>
          <div class="field-meta">${escapeHtml(t('coveragePagesTotal'))}: ${escapeHtml(String(c.paginas_totales ?? '—'))}</div>
          <div class="field-meta">${escapeHtml(t('coveragePagesAnalyzed'))}: ${escapeHtml(String(c.paginas_analizadas ?? '—'))}</div>
          <div class="field-meta">${escapeHtml(t('coveragePagesDiscarded'))}: ${escapeHtml(String(c.paginas_descartadas ?? '—'))}</div>
          <div class="field-meta">${escapeHtml(t('coveragePreliminares'))}: ${escapeHtml(prelim)}</div>
          <div class="field-meta">${escapeHtml(t('coverageFinales'))}: ${escapeHtml(finales)}</div>
        </div>
        <div class="badge">${escapeHtml(String(c.paginas_analizadas ?? '—'))}/${escapeHtml(String(c.paginas_totales ?? '—'))}</div>
      </div>`;
  });
  cont.innerHTML = html;
}

function nombreCampo(c) {
  if (currentLang === 'en' && FIELD_NAMES_EN[c.clave]) return FIELD_NAMES_EN[c.clave];
  return c.nombre;
}

function actualizarCampo(ev) {
  const idx = Number(ev.target.dataset.idx);
  const campo = ultimoResultado.propuesta.campos[idx];
  campo.valor = ev.target.value.trim() || null;
}

function activarTab(nombre) {
  $$('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === nombre));
  ['campos', 'isbd', 'avisos', 'cobertura'].forEach(tab => $('#tab-' + tab).classList.toggle('hidden', tab !== nombre));
}

async function exportar(formato) {
  if (!ultimoResultado) return;
  const payload = JSON.parse(JSON.stringify(ultimoResultado));
  try {
    const r = await fetch('/api/exportar/' + formato, {
      method: 'POST',
      credentials: 'same-origin',
      referrerPolicy: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken || '' },
      body: JSON.stringify(payload)
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Error de exportación');
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    const cd = r.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename="?([^";]+)"?/);
    a.download = m ? m[1] : 'tipo-export.' + formato;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { alert(e.message); }
}

function descargarAuditoria() {
  if (!ultimoResultado) return;
  const blob = new Blob([JSON.stringify(ultimoResultado.auditoria, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'tipo-auditoria.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

async function apagar() {
  const btn = $('#btn-apagar');
  btn.disabled = true;
  btn.textContent = t('shuttingDown');
  try {
    const r = await fetch('/api/apagar', {
      method: 'POST',
      credentials: 'same-origin',
      referrerPolicy: 'same-origin',
      headers: { 'X-CSRF-Token': csrfToken || '' }
    });
    if (!r.ok) throw new Error((await r.json()).detail || t('shutdownError'));
    $('#estado').textContent = t('shutdownStarted');
    setTimeout(() => { comprobarEstado(); }, 1500);
  } catch (_) {
    alert(t('shutdownError'));
    btn.disabled = false;
    btn.textContent = t('shutdown');
  }
}

function valorTexto(v) { return Array.isArray(v) ? v.join(' | ') : (v ?? ''); }
function escapeHtml(str) { return String(str ?? '').replace(/[&<>"]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s])); }

init();
