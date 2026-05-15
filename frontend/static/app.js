/* ============================================================================
 * Tipo — frontend logic v0.2.0-beta.7
 * Sin dependencias externas. Toda la lógica de UI vive aquí.
 * ============================================================================ */

let csrfToken = null;
let ultimoResultado = null;
let currentLang = 'es';
let modoIncognito = false;
let authStatus = null;
let modelosOllama = [];
let modelosDetalle = {};
let modeloSeleccionado = "gemma4:e4b";

/* ----- i18n ----- */
const I18N = {
  es: {
    languageLabel: 'Idioma',
    statusPreparing: 'Preparando motor local…',
    statusReady: 'Motor local listo',
    statusNoBackend: 'Sin conexión con el backend local',
    shutdown: 'Apagar',
    shuttingDown: 'Apagando…',
    shutdownStarted: 'Apagado iniciado. Puede cerrar esta pestaña en unos segundos.',
    shutdownError: 'No se pudo solicitar el apagado.',
    shutdownConfirm: 'Tipo va a detener el backend local. Se cerrará la sesión en esta pestaña y podrá cerrar la ventana del panel/instalador o usar otros servicios como desinstalar. ¿Continuar?',
    shutdownScreenTitle: 'Tipo se está apagando',
    shutdownScreenText: 'El backend local ha recibido la orden de apagado. Puede cerrar esta pestaña y, después, cerrar la ventana del panel o utilizar Detener/Desinstalar si lo necesita.',
    shutdownScreenHelp: 'Si vuelve a abrir Tipo desde el panel, el servicio arrancará de nuevo.',
    eyebrow: 'Asistente local de precatalogación',
    heroTitle: 'Extracción bibliográfica para monografías impresas',
    heroText: 'Suba el libro completo y Tipo localizará por sí mismo las zonas donde se concentran los datos descriptivos para proponer una descripción estructurada revisable. El procesamiento se realiza en local mediante Ollama.',
    notice: 'Tipo no consulta catálogos externos, no crea puntos de acceso autorizados, no asigna materias normalizadas y no modifica sistemas bibliotecarios.',
    sourcesTitle: '1. El libro',
    sourcesHelp: 'Suba el libro completo. No hace falta separar portada, verso o colofón: Tipo localiza internamente las zonas relevantes y descarta el cuerpo. También puede subir imágenes sueltas si lo prefiere.',
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
    tabMarc: 'MARC21',
    tabWarnings: 'Avisos',
    tabCoverage: 'Cobertura',
    isbdAreasIntro: 'Bloques ISBD propuestos por área, ya con su puntuación. Revíselos antes de exportar.',
    fichaCompletaTitle: 'Ficha completa (ISBD concatenada)',
    fichaCompletaCopy: 'Copiar ficha',
    copyAllIsbd: 'Copiar todo ISBD',
    copyAllMarc: 'Copiar todo MARC21',
    marcIntro: 'Registro MARC21 etiquetado. Indicador en blanco se muestra como #. Cada línea es copiable por separado.',
    noMarc: 'No se ha generado registro MARC21.',
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
    coverageNone: 'No se registró segmentación por zonas (por ejemplo, una imagen suelta).',
    copy: 'Copiar',
    copied: '✓ Copiado',
    templatesTitle: 'Valores institucionales predefinidos',
    templatesHint: '— se aplicarán si el campo extraído viene vacío',
    tplEditor: 'Editor',
    tplLugar: 'Lugar de publicación',
    tplDLPrefix: 'Prefijo D.L.',
    tplSerie: 'Serie habitual',
    templatesSave: 'Guardar como predeterminados',
    templatesClear: 'Limpiar',
    templatesSaved: 'Valores guardados.',
    templatesApplied: 'Se aplicaron valores institucionales en campos vacíos.',
    modalInstrTitle: 'Cómo usar Tipo',
    modalInstrLimitsTitle: 'Lo que Tipo NO hace',
    modalNormTitle: 'Normativa aplicada',
    modalNormIntro: 'Tipo emplea descripción ISBD por áreas y proyecta los campos atómicos a MARC21.',
    modalNormAreasTitle: 'Áreas ISBD cubiertas',
    modalNormSourcesTitle: 'Jerarquía de fuentes',
    modalNormMarcTitle: 'Proyección a MARC21',
    modalNormScopeTitle: 'Alcance',
    modalShortTitle: 'Atajos de teclado',
    incognitoOn: 'Modo incógnito activado — no se registrará auditoría detallada.',
    incognitoOff: 'Modo normal — la auditoría registra el procesamiento.',
    authTitleSetup: 'Configuración inicial de acceso',
    authTitleLogin: 'Acceso a Tipo',
    authIntroSetup: 'Cree el primer usuario administrador local. La contraseña se guarda cifrada en el volumen local de Tipo.',
    authIntroLogin: 'Introduzca su usuario y contraseña para utilizar la herramienta.',
    authUser: 'Usuario',
    authPassword: 'Contraseña',
    authPassword2: 'Repetir contraseña',
    authSubmitSetup: 'Crear usuario y entrar',
    authSubmitLogin: 'Entrar',
    authLogout: 'Cerrar sesión',
    authMismatch: 'Las contraseñas no coinciden.',
    authPasswordHelp: 'Mínimo 10 caracteres y al menos tres tipos: minúsculas, mayúsculas, números o símbolos.',
    authError: 'No se pudo completar la autenticación.',
    profile: 'Perfil',
    profileTitle: 'Perfil y seguridad',
    profileSummary: 'Usuario conectado: {user} · Rol: {role}',
    changePasswordTitle: 'Cambiar contraseña',
    currentPassword: 'Contraseña actual',
    newPassword: 'Nueva contraseña',
    changePasswordAction: 'Cambiar contraseña',
    passwordChanged: 'Contraseña actualizada.',
    userAdminTitle: 'Administración local de usuarios',
    recoveryHelp: 'Si se pierde la contraseña del administrador, use el panel de instalación de Windows: Gestionar acceso / Restablecer administrador.',
    createUserTitle: 'Crear usuario',
    createUserAction: 'Crear usuario',
    roleLabel: 'Rol',
    resetPassword: 'Restablecer contraseña',
    disableUser: 'Desactivar',
    enableUser: 'Activar',
    deleteUser: 'Eliminar',
    userCreated: 'Usuario creado.',
    userUpdated: 'Usuario actualizado.',
    modelLabel: 'Modelo Ollama',
    modelsLoading: 'Cargando modelos…',
    modelsRefresh: 'Actualizar lista de modelos',
    modelsHelp: 'Solo aparecen modelos ya descargados en Ollama.',
    modelsUnavailable: 'No se pudo obtener la lista de modelos. Revise Ollama.',
    modelsEmpty: 'No hay modelos descargados en Ollama.',
    modelDetailsTitle: 'Información del modelo',
    modelSize: 'Tamaño',
    modelFamily: 'Familia',
    modelModified: 'Fecha',
    modelCapabilities: 'Capacidades esperadas',
    modelAvailable: 'disponible',
    modelRecommended: 'recomendado',
    modelVisionWarning: 'Advertencia: este modelo no parece multimodal. Para PDFs escaneados o imágenes, use un modelo con visión.',
    diagnostic: 'Diagnóstico',
    diagnosticTitle: 'Diagnóstico operativo local',
    diagnosticRun: 'Comprobar instalación',
    diagnosticHelp: 'Comprueba backend, configuración local y límites sin enviar documentos.',
    scopeBetaTitle: 'Beta especializada',
    scopeBetaText: 'Esta versión está pensada para monografía moderna impresa. No está optimizada para manuscritos, fondo antiguo, publicaciones seriadas ni recursos electrónicos.',
    forgotPasswordHelp: '¿Ha perdido la contraseña? Use el panel de instalación: Gestionar acceso / Restablecer administrador.'
  },
  en: {
    languageLabel: 'Language',
    statusPreparing: 'Preparing local engine…',
    statusReady: 'Local engine ready',
    statusNoBackend: 'No connection to local backend',
    shutdown: 'Shut down',
    shuttingDown: 'Shutting down…',
    shutdownStarted: 'Shutdown started. You can close this tab shortly.',
    shutdownError: 'Could not request shutdown.',
    shutdownConfirm: 'Tipo will stop the local backend. The session in this tab will end and you may then close the installer/control window or use other services such as uninstall. Continue?',
    shutdownScreenTitle: 'Tipo is shutting down',
    shutdownScreenText: 'The local backend has received the shutdown command. You can close this tab and then close the control panel or use Stop/Uninstall if needed.',
    shutdownScreenHelp: 'If you open Tipo again from the panel, the service will start again.',
    eyebrow: 'Local pre-cataloging assistant',
    heroTitle: 'Bibliographic extraction for printed monographs',
    heroText: 'Upload the whole book and Tipo will locate the zones with descriptive data, proposing a reviewable structured description. Processing runs locally via Ollama.',
    notice: 'Tipo does not consult external catalogs, does not create authorized access points, does not assign normalized subjects and does not modify library systems.',
    sourcesTitle: '1. The book',
    sourcesHelp: 'Upload the whole book. No need to separate title page, verso or colophon: Tipo locates the relevant zones internally and discards the body. You may also upload single page images if preferred.',
    modeLabel: 'Mode',
    modeEssential: 'Essential',
    modeComplete: 'Complete',
    languageOutputNote: 'The proposal will be generated in the language selected for the interface.',
    process: 'Process',
    processing: 'Processing…',
    reviewable: 'Reviewable proposal',
    resultTitle: '2. Result',
    audit: 'Audit',
    tabFields: 'Fields',
    tabIsbd: 'ISBD view',
    tabMarc: 'MARC21',
    tabWarnings: 'Warnings',
    tabCoverage: 'Coverage',
    isbdAreasIntro: 'ISBD blocks proposed per area, with ISBD punctuation applied. Review before exporting.',
    fichaCompletaTitle: 'Full record (concatenated ISBD)',
    fichaCompletaCopy: 'Copy record',
    copyAllIsbd: 'Copy all ISBD',
    copyAllMarc: 'Copy all MARC21',
    marcIntro: 'Tagged MARC21 record. Blank indicator shown as #. Each line is individually copyable.',
    noMarc: 'No MARC21 record generated.',
    noFiles: 'Upload at least one file of the book.',
    noIsbd: 'Not enough data to generate ISBD view.',
    evidence: 'Evidence',
    zone: 'Zone',
    noWarnings: 'No warnings.',
    coverageTitle: 'Analyzed zones',
    coverageIntro: 'Tipo does not process the entire book: only the zones where descriptive data live.',
    coveragePagesTotal: 'Document pages',
    coveragePagesAnalyzed: 'Pages analyzed',
    coveragePagesDiscarded: 'Pages discarded',
    coveragePreliminares: 'Preliminaries',
    coverageFinales: 'End matter',
    coverageRoute: 'Processing route',
    coverageNone: 'No zone segmentation recorded.',
    copy: 'Copy',
    copied: '✓ Copied',
    templatesTitle: 'Institutional default values',
    templatesHint: '— applied if the extracted field is empty',
    tplEditor: 'Publisher',
    tplLugar: 'Place of publication',
    tplDLPrefix: 'Legal deposit prefix',
    tplSerie: 'Habitual series',
    templatesSave: 'Save as defaults',
    templatesClear: 'Clear',
    templatesSaved: 'Defaults saved.',
    templatesApplied: 'Institutional defaults applied to empty fields.',
    modalInstrTitle: 'How to use Tipo',
    modalInstrLimitsTitle: 'What Tipo does NOT do',
    modalNormTitle: 'Applied standards',
    modalNormIntro: 'Tipo uses ISBD area-based description and projects atomic fields to MARC21.',
    modalNormAreasTitle: 'ISBD areas covered',
    modalNormSourcesTitle: 'Source hierarchy',
    modalNormMarcTitle: 'MARC21 projection',
    modalNormScopeTitle: 'Scope',
    modalShortTitle: 'Keyboard shortcuts',
    incognitoOn: 'Incognito mode on — no detailed audit will be kept.',
    incognitoOff: 'Normal mode — audit records the run.',
    authTitleSetup: 'Initial access setup',
    authTitleLogin: 'Sign in to Tipo',
    authIntroSetup: 'Create the first local administrator. The password is stored as a hash in Tipo’s local volume.',
    authIntroLogin: 'Enter your username and password to use the tool.',
    authUser: 'Username',
    authPassword: 'Password',
    authPassword2: 'Repeat password',
    authSubmitSetup: 'Create user and sign in',
    authSubmitLogin: 'Sign in',
    authLogout: 'Sign out',
    authMismatch: 'The passwords do not match.',
    authPasswordHelp: 'Minimum 10 characters and at least three types: lowercase, uppercase, numbers or symbols.',
    authError: 'Authentication could not be completed.',
    profile: 'Profile',
    profileTitle: 'Profile and security',
    profileSummary: 'Signed-in user: {user} · Role: {role}',
    changePasswordTitle: 'Change password',
    currentPassword: 'Current password',
    newPassword: 'New password',
    changePasswordAction: 'Change password',
    passwordChanged: 'Password updated.',
    userAdminTitle: 'Local user administration',
    recoveryHelp: 'If the administrator password is lost, use the Windows installation panel: Access management / Reset administrator.',
    createUserTitle: 'Create user',
    createUserAction: 'Create user',
    roleLabel: 'Role',
    resetPassword: 'Reset password',
    disableUser: 'Disable',
    enableUser: 'Enable',
    deleteUser: 'Delete',
    userCreated: 'User created.',
    userUpdated: 'User updated.',
    modelLabel: 'Ollama model',
    modelsLoading: 'Loading models…',
    modelsRefresh: 'Refresh model list',
    modelsHelp: 'Only models already downloaded in Ollama are shown.',
    modelsUnavailable: 'Could not retrieve the model list. Check Ollama.',
    modelsEmpty: 'No models are downloaded in Ollama.',
    modelDetailsTitle: 'Model information',
    modelSize: 'Size',
    modelFamily: 'Family',
    modelModified: 'Date',
    modelCapabilities: 'Expected capabilities',
    modelAvailable: 'available',
    modelRecommended: 'recommended',
    modelVisionWarning: 'Warning: this model does not appear to be multimodal. For scanned PDFs or images, use a vision-capable model.',
    diagnostic: 'Diagnostics',
    diagnosticTitle: 'Local operational diagnostics',
    diagnosticRun: 'Check installation',
    diagnosticHelp: 'Checks backend, local configuration and limits without sending documents.',
    scopeBetaTitle: 'Specialised beta',
    scopeBetaText: 'This version is designed for modern printed monographs. It is not optimised for manuscripts, rare books, serials or electronic resources.',
    forgotPasswordHelp: 'Lost the password? Use the installation panel: Access management / Reset administrator.'
  }
};

const FIELD_NAMES_EN = {
  isbn: 'ISBN', deposito_legal: 'Legal deposit', lengua_texto: 'Text language',
  idioma_original: 'Original language', titulo_principal: 'Title proper',
  subtitulo: 'Subtitle or other title information', mencion_responsabilidad: 'Statement of responsibility',
  titulo_original: 'Original title', mencion_edicion: 'Edition statement',
  lugar_publicacion: 'Place of publication', editor: 'Publisher', fecha_publicacion: 'Publication date',
  fecha_copyright: 'Copyright date', extension: 'Extent', ilustraciones: 'Illustrations',
  dimensiones: 'Dimensions', tipo_contenido: 'Content type', tipo_medio: 'Media type',
  tipo_soporte: 'Carrier type', serie_transcrita: 'Series statement', nota_general: 'General note',
  nota_bibliografia: 'Bibliography note', resumen: 'Summary', nota_lengua: 'Language note'
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const t = (key) => (I18N[currentLang] && I18N[currentLang][key]) || I18N.es[key] || key;

/* ===========================================================================
 * Init
 * =========================================================================== */
async function init() {
  // Modo flotante por URL
  const params = new URLSearchParams(window.location.search);
  if (params.get('modo') === 'flotante') {
    document.body.classList.add('modo-flotante');
  }

  // Tema, densidad, incógnito desde localStorage
  document.documentElement.dataset.theme = localStorage.getItem('tipo-theme') || 'light';
  document.documentElement.dataset.density = localStorage.getItem('tipo-density') || 'cozy';
  // Modo incógnito NO se persiste — siempre arranca apagado.

  // Idioma
  currentLang = localStorage.getItem('tipo-ui-lang') || (((navigator.language || 'es').toLowerCase().startsWith('en')) ? 'en' : 'es');
  if (!['es', 'en'].includes(currentLang)) currentLang = 'es';
  $('#ui-lang').value = currentLang;
  $('#ui-lang').addEventListener('change', cambiarIdioma);
  aplicarIdioma();

  // CSRF
  try {
    const r = await fetch('/api/csrf', { cache: 'no-store', credentials: 'same-origin' });
    csrfToken = (await r.json()).token;
  } catch (_) {}

  await comprobarAutenticacion();
  if (authStatus && (!authStatus.auth_enabled || authStatus.authenticated)) {
    await cargarModelos();
  }

  comprobarEstado();
  setInterval(comprobarEstado, 4000);

  // Botones principales
  $('#ficheros').addEventListener('change', renderListaFicheros);
  $('#procesar').addEventListener('click', procesar);
  $('#modelo-ollama').addEventListener('change', () => { modeloSeleccionado = $('#modelo-ollama').value || modeloSeleccionado; localStorage.setItem('tipo-modelo-ollama', modeloSeleccionado); renderModeloInfo(modeloSeleccionado); });
  $('#btn-recargar-modelos').addEventListener('click', cargarModelos);
  $('#btn-diagnostico').addEventListener('click', cargarDiagnostico);
  $('#btn-apagar').addEventListener('click', apagar);
  $('#btn-perfil').addEventListener('click', abrirPerfil);
  $$('.tab').forEach(btn => btn.addEventListener('click', () => activarTab(btn.dataset.tab)));
  $$('[data-export]').forEach(btn => btn.addEventListener('click', () => exportar(btn.dataset.export)));
  $('#auditoria').addEventListener('click', descargarAuditoria);

  // Tema / densidad / incógnito
  $('#btn-tema').addEventListener('click', alternarTema);
  $('#btn-densidad').addEventListener('click', alternarDensidad);
  $('#btn-incognito').addEventListener('click', alternarIncognito);

  // Plantillas institucionales
  cargarPlantillas();
  $('#tpl-guardar').addEventListener('click', guardarPlantillas);
  $('#tpl-limpiar').addEventListener('click', limpiarPlantillas);

  // FABs
  $('#fab-instrucciones').addEventListener('click', () => abrirModal('modal-instrucciones'));
  $('#fab-normativa').addEventListener('click', () => abrirModal('modal-normativa'));
  $('#fab-atajos').addEventListener('click', () => abrirModal('modal-atajos'));
  $('#fab-flotante').addEventListener('click', abrirVentanaFlotante);
  // Cerrar modales: clic en backdrop o en botón ✕
  $$('.modal-backdrop').forEach(m => {
    m.addEventListener('click', (ev) => { if (ev.target === m) cerrarModales(); });
    const close = m.querySelector('.modal-close');
    if (close) close.addEventListener('click', cerrarModales);
  });

  // Atajos teclado
  $('#perfil-cambiar-pass').addEventListener('click', cambiarPasswordPropia);
  $('#crear-usuario').addEventListener('click', crearUsuarioLocal);

  document.addEventListener('keydown', manejarAtajos);
}

/* ===========================================================================
 * Idioma
 * =========================================================================== */
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

/* ===========================================================================
 * Autenticación local
 * =========================================================================== */
async function comprobarAutenticacion() {
  try {
    const r = await fetch('/api/auth/status', { cache: 'no-store', credentials: 'same-origin' });
    authStatus = await r.json();
  } catch (_) {
    authStatus = { auth_enabled: true, setup_required: false, authenticated: false };
  }
  if (authStatus.auth_enabled && !authStatus.authenticated) {
    mostrarPanelAuth(authStatus.setup_required);
    const perfil = $('#btn-perfil'); if (perfil) perfil.classList.add('hidden');
    return false;
  } else {
    ocultarPanelAuth();
    mostrarBotonLogout();
    const perfil = $('#btn-perfil'); if (perfil) perfil.classList.remove('hidden');
    return true;
  }
}

function mostrarPanelAuth(setupRequired) {
  let overlay = $('#auth-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'auth-overlay';
    overlay.className = 'auth-overlay';
    document.body.appendChild(overlay);
  }
  overlay.innerHTML = `
    <form id="auth-form" class="auth-card" autocomplete="on">
      <div class="auth-logo"><img src="/img/tipo-logo-header.png" alt="Tipo" /></div>
      <h1>${escapeHtml(setupRequired ? t('authTitleSetup') : t('authTitleLogin'))}</h1>
      <p class="muted">${escapeHtml(setupRequired ? t('authIntroSetup') : t('authIntroLogin'))}</p>
      <label><span>${escapeHtml(t('authUser'))}</span><input id="auth-user" name="username" autocomplete="username" required minlength="3" maxlength="64" /></label>
      <label><span>${escapeHtml(t('authPassword'))}</span><input id="auth-password" name="password" type="password" autocomplete="${setupRequired ? 'new-password' : 'current-password'}" required minlength="10" maxlength="256" /></label>
      ${setupRequired ? `<label><span>${escapeHtml(t('authPassword2'))}</span><input id="auth-password2" name="password2" type="password" autocomplete="new-password" required minlength="10" maxlength="256" /></label><p class="muted small">${escapeHtml(t('authPasswordHelp'))}</p>` : ''}
      <button class="primary" type="submit">${escapeHtml(setupRequired ? t('authSubmitSetup') : t('authSubmitLogin'))}</button>
      ${!setupRequired ? `<p class="muted small">${escapeHtml(t('forgotPasswordHelp'))}</p>` : ''}
      <div id="auth-error" class="error hidden"></div>
    </form>`;
  $('#auth-form').addEventListener('submit', (ev) => enviarAuth(ev, setupRequired));
  setTimeout(() => { const u = $('#auth-user'); if (u) u.focus(); }, 0);
}

function ocultarPanelAuth() {
  const overlay = $('#auth-overlay');
  if (overlay) overlay.remove();
}

function mostrarBotonLogout() {
  if ($('#btn-logout')) return;
  const cont = document.querySelector('.top-actions');
  if (!cont) return;
  const btn = document.createElement('button');
  btn.id = 'btn-logout';
  btn.className = 'ghost';
  btn.type = 'button';
  btn.textContent = t('authLogout');
  btn.addEventListener('click', logout);
  const apagarBtn = $('#btn-apagar');
  cont.insertBefore(btn, apagarBtn || null);
}

async function enviarAuth(ev, setupRequired) {
  ev.preventDefault();
  const err = $('#auth-error');
  if (err) { err.classList.add('hidden'); err.textContent = ''; }
  const username = ($('#auth-user')?.value || '').trim();
  const password = $('#auth-password')?.value || '';
  if (setupRequired) {
    const password2 = $('#auth-password2')?.value || '';
    if (password !== password2) {
      if (err) { err.textContent = t('authMismatch'); err.classList.remove('hidden'); }
      return;
    }
  }
  try {
    if (!csrfToken) {
      const r0 = await fetch('/api/csrf', { cache: 'no-store', credentials: 'same-origin' });
      csrfToken = (await r0.json()).token;
    }
    const r = await fetch(setupRequired ? '/api/auth/setup' : '/api/auth/login', {
      method: 'POST',
      credentials: 'same-origin',
      referrerPolicy: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken || '' },
      body: JSON.stringify({ username, password })
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      throw new Error(data.detail || t('authError'));
    }
    await comprobarAutenticacion();
    await cargarModelos();
  } catch (e) {
    if (err) { err.textContent = e.message || t('authError'); err.classList.remove('hidden'); }
  }
}

async function logout() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
      referrerPolicy: 'same-origin',
      headers: { 'X-CSRF-Token': csrfToken || '' }
    });
  } catch (_) {}
  const btn = $('#btn-logout');
  if (btn) btn.remove();
  const perfil = $('#btn-perfil'); if (perfil) perfil.classList.add('hidden');
  ultimoResultado = null;
  await comprobarAutenticacion();
}


/* ===========================================================================
 * Modelos Ollama
 * =========================================================================== */
async function cargarModelos() {
  const select = $('#modelo-ollama');
  const info = $('#modelos-info');
  if (!select) return;
  select.disabled = true;
  if (info) info.textContent = t('modelsLoading');
  try {
    const r = await fetch('/api/modelos', { cache: 'no-store', credentials: 'same-origin' });
    if (!r.ok) throw new Error((await r.json()).detail || t('modelsUnavailable'));
    const data = await r.json();
    const detalles = Array.isArray(data.modelos_detalle) ? data.modelos_detalle : [];
    modelosDetalle = {};
    detalles.forEach(m => { if (m && m.name) modelosDetalle[m.name] = m; });
    modelosOllama = Array.isArray(data.modelos) ? data.modelos : detalles.map(m => m.name).filter(Boolean);
    const guardado = localStorage.getItem('tipo-modelo-ollama');
    const preferido = guardado && modelosOllama.includes(guardado) ? guardado : (data.modelo_predeterminado || 'gemma4:e4b');
    select.innerHTML = '';
    if (!modelosOllama.length) {
      select.innerHTML = `<option value="">${escapeHtml(t('modelsEmpty'))}</option>`;
      select.disabled = true;
      if (info) info.textContent = t('modelsEmpty');
      renderModeloInfo(null);
      return;
    }
    modelosOllama.forEach(m => {
      const meta = modelosDetalle[m] || {};
      const opt = document.createElement('option');
      opt.value = m;
      const bits = [m];
      if (meta.recommended || m === preferido) bits.push(`— ${t('modelRecommended')}`);
      if (meta.size_human) bits.push(`(${meta.size_human})`);
      opt.textContent = bits.join(' ');
      select.appendChild(opt);
    });
    modeloSeleccionado = modelosOllama.includes(preferido) ? preferido : modelosOllama[0];
    select.value = modeloSeleccionado;
    select.disabled = false;
    if (info) info.textContent = t('modelsHelp');
    renderModeloInfo(modeloSeleccionado);
  } catch (e) {
    select.innerHTML = `<option value="">${escapeHtml(t('modelsUnavailable'))}</option>`;
    select.disabled = true;
    if (info) info.textContent = e.message || t('modelsUnavailable');
    renderModeloInfo(null, e.message || t('modelsUnavailable'));
  }
}

function renderModeloInfo(nombre, errorMsg = null) {
  const cont = $('#modelo-info');
  if (!cont) return;
  if (errorMsg) {
    cont.innerHTML = `<div class="warn">${escapeHtml(errorMsg)}</div>`;
    return;
  }
  if (!nombre || !modelosDetalle[nombre]) {
    cont.innerHTML = `<p class="muted small">${escapeHtml(t('modelsHelp'))}</p>`;
    return;
  }
  const m = modelosDetalle[nombre];
  const caps = m.capabilities || {};
  const capacidades = [];
  if (caps.texto) capacidades.push('texto');
  if (caps.vision) capacidades.push('visión');
  if (caps.json) capacidades.push('JSON');
  const familia = m.family || (Array.isArray(m.families) && m.families.length ? m.families.join(', ') : '—');
  const warnings = Array.isArray(m.warnings) ? m.warnings : [];
  const warnVision = caps.vision ? '' : `<div class="warn compact">${escapeHtml(t('modelVisionWarning'))}</div>`;
  const warnExtra = warnings.map(w => `<div class="warn compact">${escapeHtml(w)}</div>`).join('');
  cont.innerHTML = `
    <div class="model-card">
      <div class="model-card-head">
        <strong>${escapeHtml(nombre)}</strong>
        <span class="badge" data-conf="alta">${escapeHtml(t('modelAvailable'))}</span>
        ${m.recommended ? `<span class="badge role">${escapeHtml(t('modelRecommended'))}</span>` : ''}
      </div>
      <div class="model-meta-grid">
        <span>${escapeHtml(t('modelSize'))}: <strong>${escapeHtml(m.size_human || '—')}</strong></span>
        <span>${escapeHtml(t('modelFamily'))}: <strong>${escapeHtml(familia)}</strong></span>
        <span>${escapeHtml(t('modelModified'))}: <strong>${escapeHtml(m.modified_at || '—')}</strong></span>
        <span>${escapeHtml(t('modelCapabilities'))}: <strong>${escapeHtml(capacidades.join(' · ') || '—')}</strong></span>
        <span>Parámetros: <strong>${escapeHtml(m.parameter_size || '—')}</strong></span>
        <span>Cuantización: <strong>${escapeHtml(m.quantization_level || '—')}</strong></span>
      </div>
      ${warnVision}${warnExtra}
    </div>`;
}

/* ===========================================================================
 * Perfil y administración local
 * =========================================================================== */
async function abrirPerfil() {
  abrirModal('modal-perfil');
  await cargarPerfil();
}

async function cargarPerfil() {
  const resumen = $('#perfil-resumen');
  const err = $('#perfil-error');
  if (err) { err.classList.add('hidden'); err.textContent = ''; }
  try {
    const r = await fetch('/api/auth/me', { cache: 'no-store', credentials: 'same-origin' });
    if (!r.ok) throw new Error((await r.json()).detail || 'Error');
    const data = await r.json();
    const user = data.user || {};
    if (resumen) resumen.textContent = t('profileSummary').replace('{user}', user.username || '—').replace('{role}', user.role || '—');
    const admin = $('#admin-usuarios');
    if (admin) admin.classList.toggle('hidden', user.role !== 'admin');
    if (user.role === 'admin') await cargarUsuarios();
  } catch (e) {
    mostrarErrorPerfil(e.message || 'Error');
  }
}

async function cargarUsuarios() {
  const cont = $('#usuarios-lista');
  if (!cont) return;
  const r = await fetch('/api/auth/usuarios', { cache: 'no-store', credentials: 'same-origin' });
  if (!r.ok) throw new Error((await r.json()).detail || 'Error');
  const data = await r.json();
  const usuarios = Array.isArray(data.usuarios) ? data.usuarios : [];
  cont.innerHTML = usuarios.map(u => `
    <div class="user-row" data-user="${escapeAttr(u.username)}">
      <strong>${escapeHtml(u.username)}</strong>
      <span class="badge role">${escapeHtml(u.role || 'user')}</span>
      <span class="badge" data-conf="${u.disabled ? 'baja' : 'alta'}">${u.disabled ? 'desactivado' : 'activo'}</span>
      <div class="user-actions">
        <input type="password" data-reset-pass="${escapeAttr(u.username)}" placeholder="Nueva contraseña" autocomplete="new-password" />
        <button class="small-btn" type="button" data-reset-user="${escapeAttr(u.username)}">${escapeHtml(t('resetPassword'))}</button>
        <button class="small-btn ghost" type="button" data-toggle-user="${escapeAttr(u.username)}" data-disabled="${u.disabled ? '1' : '0'}">${escapeHtml(u.disabled ? t('enableUser') : t('disableUser'))}</button>
        <button class="small-btn ghost" type="button" data-delete-user="${escapeAttr(u.username)}">${escapeHtml(t('deleteUser'))}</button>
      </div>
    </div>`).join('');
  $$('[data-reset-user]').forEach(btn => btn.addEventListener('click', () => resetPasswordUsuario(btn.dataset.resetUser)));
  $$('[data-toggle-user]').forEach(btn => btn.addEventListener('click', () => cambiarEstadoUsuario(btn.dataset.toggleUser, btn.dataset.disabled !== '1')));
  $$('[data-delete-user]').forEach(btn => btn.addEventListener('click', () => eliminarUsuario(btn.dataset.deleteUser)));
}

function mostrarErrorPerfil(msg) {
  const err = $('#perfil-error');
  if (err) { err.textContent = msg; err.classList.remove('hidden'); }
}

async function cambiarPasswordPropia() {
  const current_password = $('#perfil-pass-actual').value || '';
  const new_password = $('#perfil-pass-nueva').value || '';
  try {
    const r = await fetch('/api/auth/password', {
      method: 'POST', credentials: 'same-origin', referrerPolicy: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken || '' },
      body: JSON.stringify({ current_password, new_password })
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Error');
    $('#perfil-pass-actual').value = '';
    $('#perfil-pass-nueva').value = '';
    toast(t('passwordChanged'));
  } catch (e) { mostrarErrorPerfil(e.message || 'Error'); }
}

async function crearUsuarioLocal() {
  const username = ($('#nuevo-usuario').value || '').trim();
  const password = $('#nuevo-password').value || '';
  const role = $('#nuevo-rol').value || 'user';
  try {
    const r = await fetch('/api/auth/usuarios', {
      method: 'POST', credentials: 'same-origin', referrerPolicy: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken || '' },
      body: JSON.stringify({ username, password, role })
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Error');
    $('#nuevo-usuario').value = '';
    $('#nuevo-password').value = '';
    await cargarUsuarios();
    toast(t('userCreated'));
  } catch (e) { mostrarErrorPerfil(e.message || 'Error'); }
}

async function resetPasswordUsuario(username) {
  const input = document.querySelector(`[data-reset-pass="${CSS.escape(username)}"]`);
  const password = input ? input.value : '';
  try {
    const r = await fetch('/api/auth/usuarios/' + encodeURIComponent(username) + '/password', {
      method: 'POST', credentials: 'same-origin', referrerPolicy: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken || '' },
      body: JSON.stringify({ password })
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Error');
    if (input) input.value = '';
    toast(t('passwordChanged'));
  } catch (e) { mostrarErrorPerfil(e.message || 'Error'); }
}

async function cambiarEstadoUsuario(username, disabled) {
  try {
    const r = await fetch('/api/auth/usuarios/' + encodeURIComponent(username) + '/estado', {
      method: 'POST', credentials: 'same-origin', referrerPolicy: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken || '' },
      body: JSON.stringify({ disabled })
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Error');
    await cargarUsuarios();
    toast(t('userUpdated'));
  } catch (e) { mostrarErrorPerfil(e.message || 'Error'); }
}

async function eliminarUsuario(username) {
  if (!confirm(`${t('deleteUser')}: ${username}?`)) return;
  try {
    const r = await fetch('/api/auth/usuarios/' + encodeURIComponent(username), {
      method: 'DELETE', credentials: 'same-origin', referrerPolicy: 'same-origin',
      headers: { 'X-CSRF-Token': csrfToken || '' }
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Error');
    await cargarUsuarios();
    toast(t('userUpdated'));
  } catch (e) { mostrarErrorPerfil(e.message || 'Error'); }
}

/* ===========================================================================
 * Diagnóstico operativo
 * =========================================================================== */
async function cargarDiagnostico() {
  const cont = $('#diagnostico-info');
  if (!cont) return;
  cont.classList.remove('hidden');
  cont.innerHTML = `<p class="muted small">${escapeHtml(t('diagnosticHelp'))}</p>`;
  try {
    const r = await fetch('/api/diagnostico', { cache: 'no-store', credentials: 'same-origin' });
    if (!r.ok) throw new Error((await r.json()).detail || 'Error');
    const d = await r.json();
    cont.innerHTML = `
      <div class="model-card">
        <div class="model-card-head"><strong>${escapeHtml(t('diagnosticTitle'))}</strong><span class="badge" data-conf="alta">OK</span></div>
        <div class="model-meta-grid">
          <span>Versión: <strong>${escapeHtml(d.version || '—')}</strong></span>
          <span>Solo local: <strong>${escapeHtml(d.local_only ? 'sí' : 'no')}</strong></span>
          <span>Modelo por defecto: <strong>${escapeHtml(d.modelo_por_defecto || '—')}</strong></span>
          <span>Máx. archivos: <strong>${escapeHtml(String(d.max_archivos ?? '—'))}</strong></span>
          <span>Apagado UI: <strong>${escapeHtml(d.shutdown_ui_enabled ? 'activo' : 'inactivo')}</strong></span>
          <span>Alcance: <strong>${escapeHtml(d.alcance_beta || '—')}</strong></span>
        </div>
      </div>`;
  } catch (e) {
    cont.innerHTML = `<div class="error">${escapeHtml(e.message || 'Error')}</div>`;
  }
}

/* ===========================================================================
 * Estado
 * =========================================================================== */
async function comprobarEstado() {
  const estadoEl = $('#estado');
  try {
    const r = await fetch('/api/estado', { cache: 'no-store', credentials: 'same-origin' });
    const data = await r.json();
    estadoEl.textContent = data.listo ? t('statusReady') : (data.mensaje || t('statusPreparing'));
    estadoEl.dataset.state = data.listo ? 'ready' : 'preparing';
  } catch (_) {
    estadoEl.textContent = t('statusNoBackend');
    estadoEl.dataset.state = 'error';
  }
}

/* ===========================================================================
 * Lista de ficheros
 * =========================================================================== */
function renderListaFicheros() {
  const files = Array.from($('#ficheros').files || []);
  const cont = $('#lista-ficheros');
  cont.innerHTML = '';
  files.forEach((file) => {
    const row = document.createElement('div');
    row.className = 'file-row';
    const nombreSeguro = sanearNombre(file.name);
    row.innerHTML = `<div><div class="file-name">${escapeHtml(nombreSeguro)}</div><div class="field-meta">${Math.round(file.size / 1024)} KB</div></div>`;
    cont.appendChild(row);
  });
}

/* ===========================================================================
 * Procesar
 * =========================================================================== */
async function procesar() {
  const files = Array.from($('#ficheros').files || []);
  if (!files.length) { alert(t('noFiles')); return; }
  $('#procesar').disabled = true;
  $('#procesar').textContent = t('processing');
  const fd = new FormData();
  files.forEach(f => fd.append('ficheros', f));
  fd.append('norma', 'marc21-monografias');
  fd.append('modo', $('#modo').value);
  fd.append('idioma_salida', currentLang);
  fd.append('modelo', $('#modelo-ollama').value || modeloSeleccionado || 'gemma4:e4b');
  if (modoIncognito) fd.append('incognito', '1');
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
    aplicarPlantillasAResultado();
    renderResultado();
  } catch (e) {
    $('#resultados').classList.remove('hidden');
    $('#tab-campos').innerHTML = `<div class="error">${escapeHtml(e.message)}</div>`;
  } finally {
    $('#procesar').disabled = false;
    $('#procesar').textContent = t('process');
  }
}

/* ===========================================================================
 * Render del resultado
 * =========================================================================== */
function renderResultado() {
  $('#resultados').classList.remove('hidden');
  const campos = ultimoResultado.propuesta.campos || [];
  const camposAtomicos = campos.filter(c => !(c.clave || '').startsWith('isbd_area_'));
  const bloquesIsbd = campos.filter(c => (c.clave || '').startsWith('isbd_area_'));

  // Campos atómicos con semáforo y botón de copia
  $('#tab-campos').innerHTML = camposAtomicos.map((c) => {
    const idx = campos.indexOf(c);
    const valor = valorTexto(c.valor);
    const conf = c.confianza || '';
    return `
    <div class="field" data-conf="${escapeHtml(conf)}">
      <div>
        <div class="field-name">${escapeHtml(nombreCampo(c))}</div>
        <div class="field-meta">${escapeHtml(c.id || '')} · ${escapeHtml(c.clave)}</div>
      </div>
      <div class="field-body">
        <div class="row">
          <textarea data-idx="${idx}">${escapeHtml(valor)}</textarea>
          <button class="copy-btn" type="button" data-copy="${escapeAttr(valor)}" title="${escapeAttr(t('copy'))}">⧉</button>
        </div>
        <div class="field-meta">${escapeHtml(t('evidence'))}: ${escapeHtml(c.evidencia || '—')}</div>
        ${c.zona ? `<div class="field-meta">${escapeHtml(t('zone'))}: ${escapeHtml(c.zona)}</div>` : ''}
      </div>
      <div class="badge" data-conf="${escapeHtml(conf)}">${escapeHtml(conf || '—')}</div>
    </div>`;
  }).join('');
  $$('#tab-campos textarea').forEach(tarea => tarea.addEventListener('input', actualizarCampo));
  vincularBotonesCopia('#tab-campos');

  renderIsbdAreas(bloquesIsbd);
  renderMarc();
  renderCobertura();

  const avisos = ultimoResultado.propuesta.advertencias || [];
  $('#tab-avisos').innerHTML = avisos.length
    ? avisos.map(a => `<div class="warn">${escapeHtml(a)}</div>`).join('')
    : `<p class="muted">${escapeHtml(t('noWarnings'))}</p>`;

  activarTab('campos');
}

/* ===========================================================================
 * Vista ISBD por áreas + ficha completa concatenada
 * =========================================================================== */
function renderIsbdAreas(bloques) {
  const cont = $('#tab-isbd');
  if (!bloques.length) {
    cont.innerHTML = `<pre>${escapeHtml(ultimoResultado.isbd || t('noIsbd'))}</pre>`;
    return;
  }
  const orden = ['isbd_area_0', 'isbd_area_1', 'isbd_area_2', 'isbd_area_4',
                 'isbd_area_5', 'isbd_area_6', 'isbd_area_7', 'isbd_area_8'];
  const porClave = Object.fromEntries(bloques.map(b => [b.clave, b]));

  let html = `<p class="muted small">${escapeHtml(t('isbdAreasIntro'))}</p>`;
  html += `<div class="toolbar-row"><button class="small-btn" type="button" id="btn-copy-all-isbd">⧉ ${escapeHtml(t('copyAllIsbd'))}</button></div>`;

  // Texto plano para "copiar todo". Se excluye el Área 0 de la ficha
  // concatenada porque el equivalente vive en MARC 336/337/338 y la BNE
  // y la mayoría de OPAC españoles no la muestran en la ficha legible.
  // El bloque individual del Área 0 sigue mostrándose más abajo.
  const partesCopiar = [];

  for (const k of orden) {
    const b = porClave[k];
    if (!b) continue;
    const valor = valorTexto(b.valor);
    const vacio = !valor.trim();
    if (!vacio && k !== 'isbd_area_0') partesCopiar.push(valor);
    const conf = b.confianza || '';
    html += `
      <div class="field isbd-area${vacio ? ' isbd-vacio' : ''}" data-conf="${escapeHtml(conf)}">
        <div>
          <div class="field-name">${escapeHtml(b.nombre || k)}</div>
          <div class="field-meta">${escapeHtml(b.id || '')}</div>
        </div>
        <div class="field-body">
          <div class="row">
            <pre class="isbd-bloque" style="flex:1;margin:0">${escapeHtml(valor || '—')}</pre>
            <button class="copy-btn" type="button" data-copy="${escapeAttr(valor)}" title="${escapeAttr(t('copy'))}">⧉</button>
          </div>
          ${b.zona ? `<div class="field-meta">${escapeHtml(t('zone'))}: ${escapeHtml(b.zona)}</div>` : ''}
        </div>
        <div class="badge" data-conf="${escapeHtml(conf)}">${escapeHtml(conf || '—')}</div>
      </div>`;
  }

  // Ficha completa al final. Se reconstruye desde partesCopiar (sin Área 0)
  // en vez de usar ultimoResultado.isbd, que sí incluye el Área 0.
  const fichaCompleta = partesCopiar.join('. — ');
  html += `
    <div class="ficha-completa">
      <h3>${escapeHtml(t('fichaCompletaTitle'))}</h3>
      <pre class="ficha-cuerpo">${escapeHtml(fichaCompleta)}</pre>
      <div class="ficha-actions">
        <button class="small-btn" type="button" data-copy="${escapeAttr(fichaCompleta)}">⧉ ${escapeHtml(t('fichaCompletaCopy'))}</button>
      </div>
    </div>`;

  cont.innerHTML = html;
  vincularBotonesCopia('#tab-isbd');
  $('#btn-copy-all-isbd').addEventListener('click', () => copiarAlPortapapeles(partesCopiar.join('. — '), $('#btn-copy-all-isbd')));
}

/* ===========================================================================
 * Vista MARC21
 * =========================================================================== */
function renderMarc() {
  const cont = $('#tab-marc');
  const lineas = (ultimoResultado.marc21_lineas) || [];
  if (!lineas.length) {
    cont.innerHTML = `<p class="muted">${escapeHtml(t('noMarc'))}</p>`;
    return;
  }
  let html = `<p class="muted small">${escapeHtml(t('marcIntro'))}</p>`;
  html += `<div class="toolbar-row"><button class="small-btn" type="button" id="btn-copy-all-marc">⧉ ${escapeHtml(t('copyAllMarc'))}</button></div>`;
  html += `<div class="marc-block">`;
  lineas.forEach((linea) => {
    const cuerpoHtml = pintarMarcCuerpo(linea.texto);
    html += `
      <div class="marc-line">
        <span class="marc-tag">${escapeHtml(linea.tag)}</span>
        <span class="marc-body">${cuerpoHtml}</span>
        <button class="copy-btn" type="button" data-copy="${escapeAttr(linea.texto)}" title="${escapeAttr(t('copy'))}">⧉</button>
      </div>`;
  });
  html += `</div>`;
  cont.innerHTML = html;
  vincularBotonesCopia('#tab-marc');
  const textoCompleto = (ultimoResultado.marc21_texto) || lineas.map(l => l.texto).join('\n');
  $('#btn-copy-all-marc').addEventListener('click', () => copiarAlPortapapeles(textoCompleto, $('#btn-copy-all-marc')));
}

// Convierte "020 # # $a 8433909800" en HTML con los subcampos $a destacados.
function pintarMarcCuerpo(texto) {
  // Quita los 3 primeros tokens (tag + 2 indicadores). El cuerpo es el resto.
  const tokens = texto.split(/\s+/);
  const cuerpo = tokens.slice(3).join(' ');
  // Cabecera (etiqueta + indicadores)
  const cabecera = tokens.slice(0, 3).join(' ');
  const cuerpoHtml = escapeHtml(cuerpo).replace(/(\$[a-z0-9])/g, '<span class="sf">$1</span>');
  return `<span class="muted small">${escapeHtml(cabecera).replace(/^\S+\s/, '')}</span> ${cuerpoHtml}`;
}

/* ===========================================================================
 * Cobertura
 * =========================================================================== */
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
          <div class="field-name">${escapeHtml(sanearNombre(c.archivo || c.etiqueta || '—'))}</div>
          <div class="field-meta">${escapeHtml(t('coverageRoute'))}: ${escapeHtml(c.ruta || '—')}</div>
        </div>
        <div class="field-body">
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

/* ===========================================================================
 * Tabs
 * =========================================================================== */
function activarTab(nombre) {
  $$('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === nombre));
  ['campos', 'isbd', 'marc', 'cobertura', 'avisos'].forEach(tab => {
    $('#tab-' + tab).classList.toggle('hidden', tab !== nombre);
  });
}

/* ===========================================================================
 * Edición de campo / nombres / utilidades
 * =========================================================================== */
function nombreCampo(c) {
  if (currentLang === 'en' && FIELD_NAMES_EN[c.clave]) return FIELD_NAMES_EN[c.clave];
  return c.nombre;
}
function actualizarCampo(ev) {
  const idx = Number(ev.target.dataset.idx);
  const campo = ultimoResultado.propuesta.campos[idx];
  campo.valor = ev.target.value.trim() || null;
  // El botón de copia adyacente refleja el nuevo valor
  const btn = ev.target.parentElement.querySelector('.copy-btn');
  if (btn) btn.dataset.copy = campo.valor || '';
}

/* ===========================================================================
 * Botones de copia
 * =========================================================================== */
function vincularBotonesCopia(scope) {
  $$(`${scope} [data-copy]`).forEach(btn => {
    btn.addEventListener('click', () => copiarAlPortapapeles(btn.dataset.copy, btn));
  });
}
async function copiarAlPortapapeles(texto, boton) {
  if (!texto) return;
  try {
    await navigator.clipboard.writeText(texto);
    if (boton) {
      const original = boton.textContent;
      boton.classList.add('copied');
      boton.textContent = t('copied');
      setTimeout(() => { boton.classList.remove('copied'); boton.textContent = original; }, 1400);
    }
  } catch (_) {
    // Fallback en navegadores sin Clipboard API o sin permiso
    const ta = document.createElement('textarea');
    ta.value = texto;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (_) {}
    ta.remove();
  }
}

/* ===========================================================================
 * Tema / densidad / incógnito
 * =========================================================================== */
function alternarTema() {
  const actual = document.documentElement.dataset.theme || 'light';
  const siguiente = actual === 'light' ? 'dark' : 'light';
  document.documentElement.dataset.theme = siguiente;
  localStorage.setItem('tipo-theme', siguiente);
}
function alternarDensidad() {
  const orden = ['compact', 'cozy', 'roomy'];
  const actual = document.documentElement.dataset.density || 'cozy';
  const siguiente = orden[(orden.indexOf(actual) + 1) % orden.length];
  document.documentElement.dataset.density = siguiente;
  localStorage.setItem('tipo-density', siguiente);
}
function alternarIncognito() {
  modoIncognito = !modoIncognito;
  const btn = $('#btn-incognito');
  btn.setAttribute('aria-pressed', modoIncognito ? 'true' : 'false');
  const estado = $('#estado');
  if (modoIncognito) {
    estado.textContent = t('incognitoOn');
    estado.dataset.state = 'ready';
  } else {
    comprobarEstado();
  }
}

/* ===========================================================================
 * Plantillas institucionales
 * =========================================================================== */
const CLAVES_PLANTILLAS = {
  'tpl-editor': 'editor',
  'tpl-lugar': 'lugar_publicacion',
  'tpl-dl': 'prefijo_deposito_legal',
  'tpl-serie': 'serie_transcrita'
};

function cargarPlantillas() {
  try {
    const data = JSON.parse(localStorage.getItem('tipo-templates') || '{}');
    Object.entries(CLAVES_PLANTILLAS).forEach(([id]) => {
      const el = $('#' + id); if (!el) return;
      el.value = data[id] || '';
    });
  } catch (_) {}
}
function guardarPlantillas() {
  const data = {};
  Object.keys(CLAVES_PLANTILLAS).forEach(id => {
    const el = $('#' + id); if (!el) return;
    data[id] = el.value.trim();
  });
  localStorage.setItem('tipo-templates', JSON.stringify(data));
  toast(t('templatesSaved'));
}
function limpiarPlantillas() {
  Object.keys(CLAVES_PLANTILLAS).forEach(id => { const el = $('#' + id); if (el) el.value = ''; });
  localStorage.removeItem('tipo-templates');
}
function aplicarPlantillasAResultado() {
  if (!ultimoResultado || !ultimoResultado.propuesta) return;
  let aplicados = 0;
  const plantillas = {};
  Object.entries(CLAVES_PLANTILLAS).forEach(([id, clave]) => {
    const el = $('#' + id);
    if (el && el.value.trim()) plantillas[clave] = el.value.trim();
  });
  ultimoResultado.propuesta.campos.forEach(c => {
    if (c.valor == null || c.valor === '' || (Array.isArray(c.valor) && c.valor.length === 0)) {
      if (plantillas[c.clave]) {
        c.valor = plantillas[c.clave];
        c.confianza = c.confianza || 'baja';
        c.evidencia = '(valor institucional predefinido)';
        c.estado_evidencia = 'no_verificable';
        aplicados++;
      }
    }
  });
  if (aplicados > 0) {
    const advs = ultimoResultado.propuesta.advertencias || (ultimoResultado.propuesta.advertencias = []);
    advs.push(t('templatesApplied'));
  }
}

/* ===========================================================================
 * Modales
 * =========================================================================== */
function abrirModal(id) {
  cerrarModales();
  const m = document.getElementById(id);
  if (m) m.classList.remove('hidden');
}
function cerrarModales() {
  $$('.modal-backdrop').forEach(m => m.classList.add('hidden'));
}

/* ===========================================================================
 * Ventana flotante (popup)
 * =========================================================================== */
function abrirVentanaFlotante() {
  const w = 520, h = Math.min(window.screen.availHeight - 60, 900);
  const left = window.screen.availWidth - w - 20;
  const top = 40;
  const url = window.location.pathname + '?modo=flotante';
  window.open(url, 'tipo-flotante',
    `width=${w},height=${h},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no,resizable=yes,scrollbars=yes`);
}

/* ===========================================================================
 * Atajos de teclado
 * =========================================================================== */
function manejarAtajos(ev) {
  // Cerrar modales con Esc
  if (ev.key === 'Escape') {
    if ($$('.modal-backdrop:not(.hidden)').length) { cerrarModales(); ev.preventDefault(); }
    return;
  }
  // F1 instrucciones, F2 normativa
  if (ev.key === 'F1') { abrirModal('modal-instrucciones'); ev.preventDefault(); return; }
  if (ev.key === 'F2') { abrirModal('modal-normativa'); ev.preventDefault(); return; }
  // Ctrl+Enter procesar
  if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter') {
    if (!$('#procesar').disabled) { procesar(); ev.preventDefault(); }
    return;
  }
  // Ctrl+Shift+D alternar tema
  if ((ev.ctrlKey || ev.metaKey) && ev.shiftKey && (ev.key === 'D' || ev.key === 'd')) {
    alternarTema(); ev.preventDefault(); return;
  }
  // Ctrl+K modo flotante
  if ((ev.ctrlKey || ev.metaKey) && !ev.shiftKey && (ev.key === 'K' || ev.key === 'k')) {
    abrirVentanaFlotante(); ev.preventDefault(); return;
  }
}

/* ===========================================================================
 * Exportación / auditoría / apagado
 * =========================================================================== */
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
    a.download = m ? sanearNombre(m[1]) : 'tipo-export.' + formato;
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
  if (!confirm(t('shutdownConfirm'))) return;
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
    const pantalla = $('#pantalla-apagado');
    if (pantalla) pantalla.classList.remove('hidden');
  } catch (_) {
    alert(t('shutdownError'));
    btn.disabled = false;
    btn.textContent = t('shutdown');
  }
}

/* ===========================================================================
 * Utilidades
 * =========================================================================== */
function valorTexto(v) { return Array.isArray(v) ? v.join(' | ') : (v ?? ''); }
function escapeHtml(str) { return String(str ?? '').replace(/[&<>"]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s])); }
function escapeAttr(str) { return String(str ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s])); }
function sanearNombre(n) { return String(n || '').replace(/[\\/]/g, '_').replace(/[\x00-\x1f\x7f]/g, '').slice(0, 240); }
function toast(msg) {
  const estado = $('#estado');
  const previo = estado.textContent;
  const estadoPrev = estado.dataset.state;
  estado.textContent = msg;
  estado.dataset.state = 'ready';
  setTimeout(() => { estado.textContent = previo; estado.dataset.state = estadoPrev || 'ready'; }, 1800);
}

init();
