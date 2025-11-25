const API_BASE = 'http://localhost:8001';
const statusEl = document.getElementById('status');
const loadingEl = document.getElementById('loading');
const dashboardEl = document.getElementById('dashboard');
const summaryEl = document.getElementById('summary');
const dashboardPlatform = document.getElementById('dashboardPlatform');
const projectsTableBody = document.querySelector('#projects-table tbody');
const branchesDetail = document.getElementById('branches-detail');
const branchesTableBody = document.querySelector('#branches-table tbody');
const backBtn = document.getElementById('backBtn');
const reloadBtn = document.getElementById('reloadBtn');
const downloadBtn = document.getElementById('downloadBtn');
const insightsSection = document.getElementById('insights-section');
const insightsContent = document.getElementById('insights-content');
const loadInsightsBtn = document.getElementById('loadInsightsBtn');
const recommendationsSection = document.getElementById('recommendations-section');
const recommendationsContent = document.getElementById('recommendations-content');
const loadRecommendationsBtn = document.getElementById('loadRecommendationsBtn');

let currentJobId = null;

function setStatus(msg, type='info'){
  statusEl.textContent = msg;
  statusEl.className = 'status ' + type;
}

async function loadDashboard(){
  const hash = location.hash;
  if(!hash.startsWith('#job=')){
    setStatus('No hay job_id en URL (#job=<id>)', 'error');
    return;
  }
  
  currentJobId = hash.slice(5);
  setStatus('Cargando análisis…');
  
  try {
    const res = await fetch(API_BASE + '/api/v1/jobs/' + currentJobId + '/analysis');
    if(!res.ok) throw new Error('HTTP ' + res.status);
    
    const data = await res.json();
    console.log('[Dashboard] Análisis cargado', data);
    
    if(data.analysis_data){
      loadingEl.classList.add('hidden');
      dashboardEl.classList.remove('hidden');
      renderDashboard(data);
      setStatus('✅ Análisis cargado correctamente');
    } else {
      setStatus('Sin datos de análisis', 'error');
    }
  } catch(e){
    setStatus('Error: ' + e.message, 'error');
    console.error('Error cargando dashboard', e);
  }
}

function renderDashboard(data){
  const a = data.analysis_data.analysis || {};
  
  if(data.platform){
    dashboardPlatform.textContent = 'Plataforma: ' + data.platform;
  }
  
  summaryEl.innerHTML = `
    <h2>Resumen del Análisis</h2>
    <div class="summary-grid">
      ${metric('Proyectos', a.total_projects)}
      ${metric('Ramas', a.total_branches)}
      ${metric('Ramas Inactivas', a.total_inactive_branches)}
      ${metric('Tags', a.total_tags)}
      ${metric('Releases', a.total_releases)}
      ${metric('Tags Obsoletos', a.total_obsolete_tags)}
      ${metric('Artefactos por Expirar', a.artifacts_expiring_soon)}
      ${metric('Artefactos Expirados', a.artifacts_expired)}
    </div>
  `;
  
  projectsTableBody.innerHTML = '';
  (data.analysis_data.projects || []).forEach(proj => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(proj.name)}</td>
      <td>${proj.branches.length}</td>
      <td>${proj.inactive_count || 0}</td>
      <td><button data-proj="${escapeAttr(proj.name)}" style="cursor:pointer">Ver ramas</button></td>
    `;
    projectsTableBody.appendChild(tr);
  });
  
  // Mostrar secciones LLM
  showLLMSections();
}

function showLLMSections(){
  // Mostrar acordeones LLM
  document.getElementById('insights-accordion').classList.remove('hidden');
  document.getElementById('recommendations-accordion').classList.remove('hidden');
  insightsSection.classList.remove('hidden');
  recommendationsSection.classList.remove('hidden');
}

// Función para toggle del acordeón Insights
function toggleInsights(){
  const section = document.getElementById('insights-section');
  const toggle = document.getElementById('insights-toggle');
  
  section.classList.toggle('hidden');
  
  // Rotar la flecha
  if(section.classList.contains('hidden')){
    toggle.style.transform = 'rotate(0deg)';
  } else {
    toggle.style.transform = 'rotate(180deg)';
  }
}

// Función para toggle del acordeón Recommendations
function toggleRecommendations(){
  const section = document.getElementById('recommendations-section');
  const toggle = document.getElementById('recommendations-toggle');
  
  section.classList.toggle('hidden');
  
  // Rotar la flecha
  if(section.classList.contains('hidden')){
    toggle.style.transform = 'rotate(0deg)';
  } else {
    toggle.style.transform = 'rotate(180deg)';
  }
}

projectsTableBody.addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-proj]');
  if(!btn) return;
  const projName = btn.getAttribute('data-proj');
  showBranches(projName);
});

function showBranches(projectName){
  fetch(API_BASE + '/api/v1/jobs/' + currentJobId + '/analysis')
    .then(r => r.json())
    .then(data => {
      const projects = data.analysis_data.projects || [];
      const proj = projects.find(p => p.name === projectName);
      if(!proj){
        alert('Proyecto no encontrado');
        return;
      }
      branchesDetail.classList.remove('hidden');
      branchesDetail.scrollIntoView({behavior:'smooth'});
      renderBranches(projectName, proj.branches || []);
    })
    .catch(err => {
      setStatus('Error: ' + err.message, 'error');
    });
}

function renderBranches(projectName, branches){
  branchesTableBody.innerHTML = '';
  branchesDetail.querySelector('h2').textContent = 'Ramas - ' + projectName;
  branches.forEach(b => {
    const tr = document.createElement('tr');
    const estadoClass = b.status === 'INACTIVA' ? 'badge inactiva' : (b.status === 'ACTIVA' ? 'badge activa' : 'badge latente');
    tr.innerHTML = `
      <td>${escapeHtml(b.name)}</td>
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

backBtn.addEventListener('click', () => {
  location.href = '/';
});

reloadBtn.addEventListener('click', () => {
  setStatus('Recargando…');
  location.reload();
});

downloadBtn.addEventListener('click', () => {
  if(!currentJobId){
    setStatus('No hay job para descargar', 'error');
    return;
  }
  const url = API_BASE + '/api/v1/download/' + currentJobId;
  const a = document.createElement('a');
  a.href = url;
  a.download = 'analysis_' + currentJobId + '.zip';
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// ============ DATOS DE PRUEBA (MOCK) ============

function getMockInsights() {
  return {
    executive_summary: "El repositorio contiene 20 proyectos con 58 ramas distribuidas principalmente entre backend (12), frontend (15) y devops (8). Actualmente hay 12 ramas inactivas (20.7%), indicando deuda técnica acumulada que requiere limpieza urgente.",
    risk_level: "🟠 ALTO",
    top_risks: [
      "Deuda técnica por 12 ramas inactivas acumuladas",
      "7 tags obsoletos sin limpieza desde hace > 1 año",
      "3 artefactos por expirar en menos de 7 días",
      "Conflictos potenciales en merge de feature/old-api",
      "Falta de política de retención de ramas"
    ],
    immediate_actions: [
      "Revisar y eliminar 5 ramas > 200 días (30 min)",
      "Ejecutar script de limpieza de tags (10 min)",
      "Planificar expiración de artefactos (20 min)"
    ],
    health_score: 72,
    recommendations: [
      "Implementar política automática de limpieza de ramas",
      "Documentar estándares de naming para ramas",
      "Configurar alertas para artefactos próximos a expirar",
      "Realizar auditoría trimestral de repositorios"
    ]
  };
}

function getMockRecommendations() {
  return {
    phase_1_delete_now: {
      priority: "🔴",
      branches: [
        "feature/old-api (230 días) - Reemplazado por nueva versión",
        "hotfix/bug-2023 (195 días) - Problema ya resuelto en main",
        "release/v0.9 (185 días) - Nunca se desplegó"
      ],
      rationale: "Estas ramas llevan más de 180 días sin actividad y representan deuda técnica que consume recursos",
      estimated_time: "~15 minutos",
      risks: ["Perder historial", "Conflictos pendientes"]
    },
    phase_2_review: {
      priority: "🟠",
      branches: [
        "develop/experiment (150 días) - Verificar con Juan",
        "feature/mobile-app (120 días) - Revisar MRs asociados"
      ],
      rationale: "Ramas entre 90-180 días que podrían tener valor - requieren revisión antes de eliminar",
      steps: [
        "Listar PRs/MRs asociados a cada rama",
        "Contactar a dueño original de la rama",
        "Marcar para eliminación después de confirmación"
      ]
    },
    phase_3_archive: {
      priority: "🟡",
      branches: [
        "release/v1.0 (60 días) - Probable valor histórico",
        "backup/old-config (45 días) - Documentar antes"
      ],
      rationale: "Ramas 30-90 días con posible valor histórico - considerar archivar en lugar de eliminar",
      automation: "git-archive -o backup-old-config.tar.gz v1.0:backup/old-config"
    }
  };
}

// ============ INSIGHTS CON LLM ============

loadInsightsBtn.addEventListener('click', async ()=>{
  if(!currentJobId){
    setStatus('❌ No hay job para analizar', 'error');
    return;
  }
  loadInsightsBtn.disabled = true;
  loadInsightsBtn.textContent = '⏳ Cargando insights...';
  const url = API_BASE + '/api/v1/jobs/' + currentJobId + '/insights';
  console.log(`[INSIGHTS] Llamando a ${url}`);
  try {
    const res = await fetch(url);
    console.log(`[INSIGHTS] Respuesta: ${res.status} ${res.statusText}`);
    if(!res.ok){
      console.error('[INSIGHTS] Error HTTP:', res.status);
      if(res.status === 503) {
        // Si LLM no disponible, usar datos de prueba
        console.warn('[INSIGHTS] LLM no disponible (503), usando mock data');
        renderInsights(getMockInsights());
        setStatus('⚠️ Usando datos de ejemplo (LLM no disponible)', 'info');
      } else {
        throw new Error('HTTP ' + res.status);
      }
    } else {
      const data = await res.json();
      console.log('[INSIGHTS] Datos recibidos:', data.insights);
      renderInsights(data.insights);
      setStatus('✅ Insights cargados desde LLM ✨', 'success');
    }
  } catch(e){
    console.error('[INSIGHTS] Error en Insights:', e);
    insightsContent.innerHTML = `<div style="padding:1rem;background:#2d1b2e;border:1px solid #ef4444;border-radius:0.5rem;color:#fca5a5"><strong>❌ Error:</strong> ${escapeHtml(e.message)}</div>`;
    setStatus('❌ Error al cargar insights', 'error');
  } finally {
    loadInsightsBtn.disabled = false;
    loadInsightsBtn.textContent = '📊 Cargar Insights';
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
  const url = API_BASE + '/api/v1/jobs/' + currentJobId + '/recommendations';
  console.log(`[RECOMMENDATIONS] Llamando a ${url}`);
  try {
    const res = await fetch(url);
    console.log(`[RECOMMENDATIONS] Respuesta: ${res.status} ${res.statusText}`);
    if(!res.ok){
      console.error('[RECOMMENDATIONS] Error HTTP:', res.status);
      if(res.status === 503) {
        // Si LLM no disponible, usar datos de prueba
        console.warn('[RECOMMENDATIONS] LLM no disponible (503), usando mock data');
        renderRecommendations(getMockRecommendations());
        setStatus('⚠️ Usando datos de ejemplo (LLM no disponible)', 'info');
      } else {
        throw new Error('HTTP ' + res.status);
      }
    } else {
      const data = await res.json();
      console.log('[RECOMMENDATIONS] Datos recibidos:', data.cleanup_plan);
      renderRecommendations(data.cleanup_plan);
      setStatus('✅ Recomendaciones cargadas desde LLM ✨', 'success');
    }
  } catch(e){
    console.error('[RECOMMENDATIONS] Error:', e);
    recommendationsContent.innerHTML = `<div style="padding:1rem;background:#2d1b2e;border:1px solid #ef4444;border-radius:0.5rem;color:#fca5a5"><strong>❌ Error:</strong> ${escapeHtml(e.message)}</div>`;
    setStatus('❌ Error al cargar recomendaciones', 'error');
  } finally {
    loadRecommendationsBtn.disabled = false;
    loadRecommendationsBtn.textContent = '📋 Cargar Recomendaciones';
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

// Cargar al iniciar
window.addEventListener('load', loadDashboard);
