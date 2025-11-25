const form = document.getElementById('analyze-form');
const statusEl = document.getElementById('status');
const platformInfo = document.getElementById('platformInfo');
const loadLatestBtn = document.getElementById('loadLatestBtn');
const dashboardEl = document.getElementById('dashboard');
const summaryEl = document.getElementById('summary');
const projectsTableBody = document.querySelector('#projects-table tbody');
const branchesDetail = document.getElementById('branches-detail');
const branchesTableBody = document.querySelector('#branches-table tbody');
const backBtn = document.getElementById('backBtn');
const reloadBtn = document.getElementById('reloadBtn');
const downloadBtn = document.getElementById('downloadBtn');
const dashboardPlatform = document.getElementById('dashboardPlatform');
const insightsSection = document.getElementById('insights-section');
const insightsContent = document.getElementById('insights-content');
const loadInsightsBtn = document.getElementById('loadInsightsBtn');
const recommendationsSection = document.getElementById('recommendations-section');
const recommendationsContent = document.getElementById('recommendations-content');
const loadRecommendationsBtn = document.getElementById('loadRecommendationsBtn');

let currentJobId = null;
const API_BASE = 'http://localhost:8001';
let analyzing = false;
let pollingInterval = null;
let analysisStartTime = null;

// Etapas de progreso con emojis y descripciones
const progressStages = [
  { progress: 0.05, label: '🔍 Detectando plataforma', minWait: 0 },
  { progress: 0.15, label: '⚙️ Conectando y cargando proyectos', minWait: 2 },
  { progress: 0.30, label: '📚 Leyendo ramas', minWait: 5 },
  { progress: 0.50, label: '🏷️ Procesando tags y releases', minWait: 10 },
  { progress: 0.70, label: '📦 Analizando artefactos', minWait: 15 },
  { progress: 0.90, label: '📊 Generando reporte', minWait: 20 },
  { progress: 1.0, label: '✅ Completando', minWait: 25 }
];

function setStatus(msg, type = 'info') {
  statusEl.textContent = msg;
  statusEl.className = 'status ' + type;
}

function getETAMessage(progress) {
  if (!analysisStartTime) return '';
  const elapsed = Math.round((Date.now() - analysisStartTime) / 1000);
  if (progress <= 0 || progress >= 1) return '';
  const estimated = Math.round(elapsed / progress);
  const remaining = Math.max(0, estimated - elapsed);
  return ` ⏱️ ${remaining}s`;
}

function getProgressLabel(progress) {
  for (let i = progressStages.length - 1; i >= 0; i--) {
    if (progress >= progressStages[i].progress) {
      return progressStages[i].label;
    }
  }
  return '🚀 Iniciando';
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  stopPolling();
  branchesDetail.classList.add('hidden');
  dashboardEl.classList.add('hidden');
  projectsTableBody.innerHTML = '';
  summaryEl.innerHTML = '';

  if(analyzing){
    console.warn('[UI] Ya hay un análisis en curso');
    return;
  }

  const repository_url = document.getElementById('repository_url').value.trim();
  const token = document.getElementById('token').value.trim();
  const project_path = document.getElementById('project_path').value.trim() || null;
  const auto_discover_groups = document.getElementById('auto_discover_groups').value === 'true';
  const analysis_mode = document.getElementById('analysis_mode').value;
  const active_days = parseInt(document.getElementById('active_days').value, 10) || 30;
  const stale_days = parseInt(document.getElementById('stale_days').value, 10) || 90;

  if(!repository_url || !token){
    setStatus('❌ Repository URL y Token son requeridos', 'error');
    return;
  }

  setStatus('🚀 Lanzando análisis...');
  try {
    analyzing = true;
    document.getElementById('startBtn').disabled = true;
    
    const res = await fetch(API_BASE + '/api/v1/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repository_url, token, project_path, auto_discover_groups, analysis_mode, active_days, stale_days })
    });
    
    if(!res.ok){
      const err = await res.json().catch(()=>({detail:res.statusText}));
      throw new Error(err.detail || 'Error al iniciar');
    }
    
    const data = await res.json();
    currentJobId = data.job_id;
    platformInfo.textContent = '🌐 Plataforma: ' + (data.platform || 'desconocida');
    analysisStartTime = Date.now();
    
    setStatus('⏳ Análisis iniciado - procesando...');
    location.hash = '#job=' + currentJobId;
    startPolling();
  } catch (err) {
    setStatus('❌ Error: ' + err.message, 'error');
  } finally {
    analyzing = false;
    document.getElementById('startBtn').disabled = false;
  }
});

function startPolling(){
  stopPolling();
  pollingInterval = setInterval(fetchStatus, 2000);
  fetchStatus();
}

function stopPolling(){
  if(pollingInterval){
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
}

async function fetchStatus(){
  if(!currentJobId) return;
  try {
    const url = API_BASE + '/api/v1/jobs/' + currentJobId + '?t=' + Date.now();
    const res = await fetch(url);
    if(!res.ok) throw new Error('HTTP ' + res.status);
    
    const job = await res.json();
    renderJob(job);
    
    if(job.status === 'completed' || job.status === 'failed'){
      stopPolling();
    }
  } catch (e){
    setStatus('❌ Error status: ' + e.message, 'error');
  }
}

function renderJob(job){
  const { status, progress, message } = job;
  const percent = Math.round(progress * 100);
  const label = getProgressLabel(progress);
  const eta = getETAMessage(progress);
  
  let emoji = '⏳';
  if (status === 'completed') emoji = '✅';
  else if (status === 'failed') emoji = '❌';
  else if (progress >= 0.75) emoji = '🔥';
  else if (progress >= 0.5) emoji = '⚙️';
  
  setStatus(`${emoji} ${label} - ${percent}%${eta}`);
  
  if(job.platform){
    platformInfo.textContent = '🌐 Plataforma: ' + job.platform;
  }
  
  if(status === 'completed'){
    setStatus('✅ Análisis completado. Redirigiendo…');
    showLLMSections();
    setTimeout(()=>{
      console.log('[APP] Redirigiendo al dashboard con job_id:', job.job_id);
      location.href = '/dashboard.html#job=' + job.job_id;
    }, 1000);
  }
}

function renderDashboard(data){
  dashboardEl.classList.remove('hidden');
  const a = data.analysis || {};
  summaryEl.innerHTML = `
    <h2>📊 Resumen</h2>
    <div class="summary-grid">
      ${metric('📁 Proyectos', a.total_projects)}
      ${metric('🌿 Ramas', a.total_branches)}
      ${metric('⚠️ Inactivas', a.total_inactive_branches)}
      ${metric('🏷️ Tags', a.total_tags)}
      ${metric('📦 Releases', a.total_releases)}
      ${metric('🗑️ Obsoletos', a.total_obsolete_tags)}
      ${metric('⏰ Por Expirar', a.artifacts_expiring_soon)}
      ${metric('💥 Expirados', a.artifacts_expired)}
    </div>
  `;

  projectsTableBody.innerHTML = '';
  (data.projects || []).forEach(proj => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>📂 ${escapeHtml(proj.name)}</td>
      <td>${proj.branches.length}</td>
      <td>${proj.inactive_count || 0}</td>
      <td><button data-proj="${escapeAttr(proj.name)}">Ver ramas</button></td>
    `;
    projectsTableBody.appendChild(tr);
  });
}

projectsTableBody.addEventListener('click', (e)=>{
  const btn = e.target.closest('button[data-proj]');
  if(!btn) return;
  const projName = btn.getAttribute('data-proj');
  showBranches(projName);
});

function showBranches(projectName){
  fetch(API_BASE + '/api/v1/jobs/' + currentJobId + '/analysis')
    .then(r=>r.json())
    .then(data => {
      const projects = (data.analysis_data && data.analysis_data.projects) || [];
      const proj = projects.find(p => p.name === projectName);
      if(!proj){
        alert('Proyecto no encontrado');
        return;
      }
      branchesDetail.classList.remove('hidden');
      branchesDetail.scrollIntoView({behavior:'smooth'});
      renderBranches(projectName, proj.branches || []);
    })
    .catch(err => setStatus('❌ Error: ' + err.message, 'error'));
}

function renderBranches(projectName, branches){
  branchesTableBody.innerHTML = '';
  branchesDetail.querySelector('h2').textContent = '🌿 Ramas - ' + projectName;
  branches.forEach(b => {
    const tr = document.createElement('tr');
    const statusEmoji = b.status === 'INACTIVA' ? '⚠️' : (b.status === 'ACTIVA' ? '✅' : '⏳');
    const estadoClass = b.status === 'INACTIVA' ? 'badge inactiva' : 'badge activa';
    tr.innerHTML = `
      <td>${statusEmoji} ${escapeHtml(b.name)}</td>
      <td>${escapeHtml(b.last_commit_date || '-')}</td>
      <td>${b.days_since_last_commit ?? '-'}</td>
      <td><span class="${estadoClass}">${escapeHtml(b.status || 'DESCONOCIDO')}</span></td>
    `;
    branchesTableBody.appendChild(tr);
  });
}

function metric(label, value){
  return `<div class="metric"><h3>${escapeHtml(label)}</h3><p>${value ?? 0}</p></div>`;
}

function escapeHtml(s){
  return (s==null?'':String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
}

function escapeAttr(s){
  return escapeHtml(s).replace(/"/g,'&quot;');
}

window.addEventListener('load', () => {
  const hash = location.hash;
  if(hash.startsWith('#job=')){
    currentJobId = hash.slice(5);
    setStatus('⏳ Cargando job existente ' + currentJobId);
    analysisStartTime = Date.now();
    startPolling();
  }
});

loadLatestBtn.addEventListener('click', async ()=>{
  try {
    setStatus('🔍 Buscando últimos análisis...');
    const r = await fetch(API_BASE + '/api/v1/outputs');
    const j = await r.json();
    if(!j.outputs.length){
      setStatus('ℹ️ No hay análisis previos');
      return;
    }
    currentJobId = j.outputs[0].job_id;
    location.hash = '#job=' + currentJobId;
    setStatus('⏳ Cargando job ' + currentJobId);
    analysisStartTime = Date.now();
    startPolling();
  } catch(e){
    setStatus('❌ Error: ' + e.message,'error');
  }
});

function fetchStatusCompleted(jobId){
  return fetch(API_BASE + '/api/v1/jobs/' + jobId + '/analysis').then(r=>r.json());
}

backBtn.addEventListener('click', ()=>{
  location.href = 'http://localhost:3000';
});

reloadBtn.addEventListener('click', ()=>{
  setStatus('🔄 Recargando…');
  location.reload();
});

downloadBtn.addEventListener('click', ()=>{
  if(!currentJobId){
    setStatus('❌ No hay job para descargar', 'error');
    return;
  }
  const url = API_BASE + '/api/v1/download/' + currentJobId;
  setStatus('⬇️ Descargando…');
  const a = document.createElement('a');
  a.href = url;
  a.download = 'analysis_'+currentJobId+'.zip';
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// ============ INSIGHTS CON LLM ============

loadInsightsBtn.addEventListener('click', async ()=>{
  if(!currentJobId){
    setStatus('❌ No hay job para analizar', 'error');
    return;
  }
  loadInsightsBtn.disabled = true;
  loadInsightsBtn.textContent = '⏳ Cargando insights...';
  try {
    const res = await fetch(API_BASE + '/api/v1/jobs/' + currentJobId + '/insights');
    if(!res.ok){
      if(res.status === 503) throw new Error('LLM no disponible');
      throw new Error('HTTP ' + res.status);
    }
    const data = await res.json();
    renderInsights(data.insights);
  } catch(e){
    insightsContent.innerHTML = `<p style="color:#ef4444">❌ Error: ${escapeHtml(e.message)}</p>`;
  } finally {
    loadInsightsBtn.disabled = false;
    loadInsightsBtn.textContent = 'Cargar Insights';
  }
});

function renderInsights(insights) {
  const riskEmoji = insights.risk_level ? insights.risk_level.split(' ')[0] : '❓';
  
  let html = `
    <div style="margin-bottom:1.5rem">
      <h3 style="color:#a78bfa;margin-bottom:0.5rem">📊 Resumen Ejecutivo ${riskEmoji}</h3>
      <p style="line-height:1.6;color:#cbd5e1">${escapeHtml(insights.executive_summary)}</p>
    </div>
    
    <div style="margin-bottom:1.5rem">
      <h3 style="color:#f87171;margin-bottom:0.5rem">⚠️ Riesgos Principales (${riskEmoji} ${insights.risk_level})</h3>
      <ul style="color:#cbd5e1;padding-left:1.5rem">
  `;
  
  (insights.top_risks || []).forEach(risk => {
    html += `<li style="margin-bottom:0.5rem">${escapeHtml(risk)}</li>`;
  });
  
  html += `</ul></div>`;
  
  html += `<div style="margin-bottom:1.5rem">
      <h3 style="color:#4ade80;margin-bottom:0.5rem">🎯 Acciones Inmediatas</h3>
      <ul style="color:#cbd5e1;padding-left:1.5rem">
  `;
  
  (insights.immediate_actions || []).forEach(action => {
    html += `<li style="margin-bottom:0.5rem">${escapeHtml(action)}</li>`;
  });
  
  html += `</ul></div>`;
  
  html += `<div style="background:#1e293b;border-left:4px solid #8b5cf6;padding:1rem;border-radius:0.5rem;margin-bottom:1.5rem">
      <p style="color:#a78bfa;font-weight:600;margin-bottom:0.5rem">💚 Health Score: ${insights.health_score || 0}/100</p>
      <div style="background:#0f172a;height:1rem;border-radius:0.25rem;overflow:hidden">
        <div style="background:linear-gradient(90deg,#8b5cf6,#a78bfa);height:100%;width:${insights.health_score || 0}%"></div>
      </div>
  </div>`;
  
  html += `<div><h3 style="color:#60a5fa;margin-bottom:0.5rem">💡 Recomendaciones</h3>
      <ul style="color:#cbd5e1;padding-left:1.5rem">
  `;
  
  (insights.recommendations || []).forEach(rec => {
    html += `<li style="margin-bottom:0.5rem">${escapeHtml(rec)}</li>`;
  });
  
  html += `</ul></div>`;
  
  insightsContent.innerHTML = html;
}

loadRecommendationsBtn.addEventListener('click', async ()=>{
  if(!currentJobId){
    setStatus('❌ No hay job para analizar', 'error');
    return;
  }
  loadRecommendationsBtn.disabled = true;
  loadRecommendationsBtn.textContent = '⏳ Cargando plan...';
  try {
    const res = await fetch(API_BASE + '/api/v1/jobs/' + currentJobId + '/recommendations');
    if(!res.ok){
      if(res.status === 503) throw new Error('LLM no disponible');
      throw new Error('HTTP ' + res.status);
    }
    const data = await res.json();
    renderRecommendations(data.cleanup_plan);
  } catch(e){
    recommendationsContent.innerHTML = `<p style="color:#ef4444">❌ Error: ${escapeHtml(e.message)}</p>`;
  } finally {
    loadRecommendationsBtn.disabled = false;
    loadRecommendationsBtn.textContent = 'Cargar Recomendaciones';
  }
});

function renderRecommendations(plan) {
  let html = ``;
  
  // Fase 1
  const phase1 = plan.phase_1_delete_now || {};
  html += `<div style="background:#2d1b2e;border-left:4px solid #ef4444;padding:1rem;margin-bottom:1.5rem;border-radius:0.5rem">
    <h3 style="color:#f87171;margin-bottom:0.5rem">${phase1.priority} FASE 1: Eliminar Ahora</h3>
    <p style="color:#cbd5e1;margin-bottom:0.5rem"><strong>Justificación:</strong> ${escapeHtml(phase1.rationale || '')}</p>
    <p style="color:#cbd5e1;margin-bottom:0.5rem"><strong>Ramas:</strong></p>
    <ul style="color:#cbd5e1;padding-left:1.5rem">
  `;
  (phase1.branches || []).forEach(branch => {
    html += `<li>${escapeHtml(branch)}</li>`;
  });
  html += `</ul>`;
  if(phase1.risks) {
    html += `<p style="color:#fca5a5;margin-top:0.5rem"><strong>⚠️ Riesgos:</strong> ${(phase1.risks || []).join(', ')}</p>`;
  }
  if(phase1.estimated_time) {
    html += `<p style="color:#cbd5e1;margin-top:0.5rem"><strong>⏱️ Tiempo:</strong> ${phase1.estimated_time}</p>`;
  }
  html += `</div>`;
  
  // Fase 2
  const phase2 = plan.phase_2_review || {};
  html += `<div style="background:#1f2d3d;border-left:4px solid #f97316;padding:1rem;margin-bottom:1.5rem;border-radius:0.5rem">
    <h3 style="color:#fb923c;margin-bottom:0.5rem">${phase2.priority} FASE 2: Revisar Primero</h3>
    <p style="color:#cbd5e1;margin-bottom:0.5rem"><strong>Justificación:</strong> ${escapeHtml(phase2.rationale || '')}</p>
    <p style="color:#cbd5e1;margin-bottom:0.5rem"><strong>Ramas:</strong></p>
    <ul style="color:#cbd5e1;padding-left:1.5rem">
  `;
  (phase2.branches || []).forEach(branch => {
    html += `<li>${escapeHtml(branch)}</li>`;
  });
  html += `</ul>`;
  if(phase2.steps) {
    html += `<p style="color:#cbd5e1;margin-top:0.5rem"><strong>📋 Pasos:</strong></p><ol style="color:#cbd5e1;padding-left:1.5rem">`;
    phase2.steps.forEach(step => {
      html += `<li>${escapeHtml(step)}</li>`;
    });
    html += `</ol>`;
  }
  html += `</div>`;
  
  // Fase 3
  const phase3 = plan.phase_3_archive || {};
  html += `<div style="background:#1f2d22;border-left:4px solid #eab308;padding:1rem;margin-bottom:1.5rem;border-radius:0.5rem">
    <h3 style="color:#facc15;margin-bottom:0.5rem">${phase3.priority} FASE 3: Archivar</h3>
    <p style="color:#cbd5e1;margin-bottom:0.5rem"><strong>Justificación:</strong> ${escapeHtml(phase3.rationale || '')}</p>
    <p style="color:#cbd5e1;margin-bottom:0.5rem"><strong>Ramas:</strong></p>
    <ul style="color:#cbd5e1;padding-left:1.5rem">
  `;
  (phase3.branches || []).forEach(branch => {
    html += `<li>${escapeHtml(branch)}</li>`;
  });
  html += `</ul>`;
  if(phase3.automation) {
    html += `<p style="color:#cbd5e1;margin-top:0.5rem"><strong>🤖 Automatización:</strong> ${escapeHtml(phase3.automation)}</p>`;
  }
  html += `</div>`;
  
  recommendationsContent.innerHTML = html;
}

// Mostrar secciones de insights cuando el análisis se completa
function showLLMSections() {
  insightsSection.classList.remove('hidden');
  recommendationsSection.classList.remove('hidden');
}
