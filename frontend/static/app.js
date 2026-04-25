let csrfToken = null;
let ultimoResultado = null;
let currentLang = 'es';
const etiquetasSugeridas = ['portada', 'verso de portada', 'cubierta', 'contracubierta', 'lomo', 'colofón', 'índice', 'bibliografía', 'otra'];

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
    heroText: 'Suba imágenes del libro y Tipo propondrá datos descriptivos estructurados para revisión profesional. El procesamiento se realiza en local mediante Ollama.',
    notice: 'Tipo no consulta catálogos externos, no crea puntos de acceso autorizados, no asigna materias normalizadas y no modifica sistemas bibliotecarios.',
    sourcesTitle: '1. Fuentes del libro',
    sourcesHelp: 'Añada portada, verso de portada, cubierta, contracubierta, lomo, colofón, índice u otras imágenes.',
    modeLabel: 'Modo',
    modeEssential: 'Esencial',
    modeComplete: 'Completo',
    languageOutputNote: 'La propuesta se generará en el idioma seleccionado para la interfaz.',
    process: 'Procesar conjunto',
    processing: 'Procesando…',
    reviewable: 'Propuesta revisable',
    resultTitle: '2. Resultado',
    audit: 'Auditoría',
    tabFields: 'Campos',
    tabIsbd: 'Vista ISBD',
    tabWarnings: 'Avisos',
    noFiles: 'Sube al menos una imagen o documento.',
    noIsbd: 'Sin datos suficientes para generar vista ISBD.',
    evidence: 'Evidencia',
    noWarnings: 'Sin advertencias.'
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
    heroText: 'Upload images of the book and Tipo will propose structured descriptive data for professional review. Processing is performed locally with Ollama.',
    notice: 'Tipo does not query external catalogues, does not create authorized access points, does not assign controlled subjects, and does not modify library systems.',
    sourcesTitle: '1. Book sources',
    sourcesHelp: 'Add title page, verso of title page, cover, back cover, spine, colophon, table of contents or other images.',
    modeLabel: 'Mode',
    modeEssential: 'Essential',
    modeComplete: 'Complete',
    languageOutputNote: 'The proposal will be generated in the selected interface language.',
    process: 'Process set',
    processing: 'Processing…',
    reviewable: 'Reviewable proposal',
    resultTitle: '2. Result',
    audit: 'Audit',
    tabFields: 'Fields',
    tabIsbd: 'ISBD view',
    tabWarnings: 'Warnings',
    noFiles: 'Upload at least one image or document.',
    noIsbd: 'Not enough data to generate the ISBD view.',
    evidence: 'Evidence',
    noWarnings: 'No warnings.'
  }
};

const FIELD_NAMES_EN = {
  isbn: 'ISBN',
  lengua_texto: 'Language of text',
  titulo_principal: 'Title proper',
  subtitulo: 'Subtitle or other title information',
  mencion_responsabilidad: 'Transcribed statement of responsibility',
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

function renderListaFicheros() {
  const files = Array.from($('#ficheros').files || []);
  const cont = $('#lista-ficheros');
  cont.innerHTML = '';
  files.forEach((file, idx) => {
    const row = document.createElement('div');
    row.className = 'file-row';
    row.innerHTML = `<div><div class="file-name">${escapeHtml(file.name)}</div><div class="field-meta">${Math.round(file.size / 1024)} KB</div></div>`;
    const select = document.createElement('select');
    select.className = 'etiqueta';
    etiquetasSugeridas.forEach(e => {
      const o = document.createElement('option');
      o.value = e;
      o.textContent = e;
      if (idx < etiquetasSugeridas.length && e === etiquetasSugeridas[idx]) o.selected = true;
      select.appendChild(o);
    });
    row.appendChild(select);
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
  const etiquetas = $$('.etiqueta').map(x => x.value);
  fd.append('etiquetas', JSON.stringify(etiquetas));
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
      </div>
      <div class="badge">${escapeHtml(c.confianza || 'sin valor')}<br>${escapeHtml(c.estado_evidencia || '')}</div>
    </div>`).join('');
  $$('#tab-campos textarea').forEach(tarea => tarea.addEventListener('input', actualizarCampo));
  $('#isbd-text').textContent = ultimoResultado.isbd || t('noIsbd');
  const avisos = ultimoResultado.propuesta.advertencias || [];
  $('#tab-avisos').innerHTML = avisos.length ? avisos.map(a => `<div class="warn">${escapeHtml(a)}</div>`).join('') : `<p class="muted">${escapeHtml(t('noWarnings'))}</p>`;
  activarTab('campos');
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
  ['campos', 'isbd', 'avisos'].forEach(tab => $('#tab-' + tab).classList.toggle('hidden', tab !== nombre));
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
