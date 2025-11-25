"""
API para ejecutar el GitLabAgent (LangGraph) como servicio REST
- Lee credenciales desde .env (GITLAB_URL, GITLAB_TOKEN)
- Permite pasar project_path o group_path
- Permite override de parámetros (active_days, stale_days, etc.)
- Corre en background y expone endpoints de estado y descarga
"""

import os
import uuid
import shutil
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Tu agente
from AS_langgraphEnabler import RepositoryAgent, AnalysisMode, PlatformDetector

# LLM Analyzer
try:
    from LLMAnalyzer import get_llm_analyzer
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    logger.warning("⚠️ LLMAnalyzer no disponible. Funcionando sin insights de LLM.")

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger("gitlab-agent-api")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# LLM Analyzer
try:
    from LLMAnalyzer import get_llm_analyzer
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    logger.warning("⚠️ LLMAnalyzer no disponible. Funcionando sin insights de LLM.")

# ──────────────────────────────────────────────────────────────────────────────
# APP & CORS
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="GitLab Agent API",
    description="API para análisis de repositorios GitLab con LangGraph",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# Servir archivos estáticos del frontend
WEB_DIR = BASE_DIR / "web"
if WEB_DIR.exists():
    logger.info(f"✅ Web estático disponible en {WEB_DIR}")
else:
    logger.warning(f"⚠️ Directorio web no encontrado: {WEB_DIR}")

# ──────────────────────────────────────────────────────────────────────────────
# STORES THREAD-SAFE
# ──────────────────────────────────────────────────────────────────────────────
jobs_lock = threading.Lock()
jobs_store: Dict[str, Dict[str, Any]] = {}   # job_id -> estado/resultados

def _persist_job(job: Dict[str, Any]):
    """Guarda el estado del job en outputs/<job_id>/job.json"""
    try:
        import json
        job_id = job.get("job_id")
        if not job_id:
            return
        jdir = OUTPUTS_DIR / job_id
        jdir.mkdir(exist_ok=True)
        with open(jdir / "job.json", "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"No se pudo persistir job {job.get('job_id')}: {e}")

def _rehydrate_jobs_from_disk():
    """Carga jobs desde outputs/*/job.json si no están en memoria."""
    import json
    loaded = 0
    for job_dir in OUTPUTS_DIR.iterdir():
        if not job_dir.is_dir():
            continue
        jfile = job_dir / "job.json"
        if not jfile.exists():
            continue
        try:
            with open(jfile, 'r', encoding='utf-8') as f:
                job = json.load(f)
            jid = job.get('job_id') or job_dir.name
            with jobs_lock:
                if jid not in jobs_store:
                    jobs_store[jid] = job
                    loaded += 1
        except Exception as e:
            logger.warning(f"No se pudo rehidratar {jfile}: {e}")
    if loaded:
        logger.info(f"♻️ Rehidratados {loaded} jobs desde disco")

def create_job() -> str:
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs_store[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0.0,
            "message": "Job creado",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "result": None,
            "error": None,
            "platform": "unknown",
        }
    _persist_job(jobs_store[job_id])
    return job_id

def update_job(job_id: str, **fields):
    with jobs_lock:
        job = jobs_store.get(job_id)
        if not job:
            return
        for k, v in fields.items():
            if v is not None:
                job[k] = v
        job["updated_at"] = datetime.now().isoformat()
    _persist_job(job)

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with jobs_lock:
        j = jobs_store.get(job_id)
        return dict(j) if j else None

def load_analysis_data(output_dir: str) -> Optional[Dict[str, Any]]:
    """Lee los JSONs de salida del análisis y retorna los datos estructurados."""
    import json
    
    output_path = Path(output_dir)
    if not output_path.exists():
        return None
    
    analysis_data = {
        "groups": [],
        "projects": [],
        "analysis": {
            "total_projects": 0,
            "total_branches": 0,
            "total_tags": 0,
            "total_releases": 0,
            "total_inactive_branches": 0,
            "total_obsolete_tags": 0,
            "artifacts_expiring_soon": 0,
            "artifacts_expired": 0,
        },
        "raw_inventory": [],
        "inactive_branches": [],
        "maintenance_report": None,
    }
    
    # Leer inventario de ramas
    inventory_file = output_path / "inventario_repos_ramas.json"
    if inventory_file.exists():
        try:
            with open(inventory_file, 'r', encoding='utf-8') as f:
                branches_data = json.load(f)
            
            # Guardar inventario completo en bruto
            analysis_data["raw_inventory"] = branches_data
            
            # Agrupar por proyecto con información detallada
            projects_dict = {}
            for branch_info in branches_data:
                project_name = branch_info.get('project', 'unknown')
                if project_name not in projects_dict:
                    projects_dict[project_name] = {
                        'name': project_name,
                        'project_id': branch_info.get('project_id'),
                        'url': f"https://umane.emeal.nttdata.com/git/{project_name}",  # Ajustar URL según plataforma
                        'branches': [],
                        'tags': [],
                        'releases': [],
                        'inactive_count': 0,
                    }
                
                # Agregar información detallada de la rama
                branch = {
                    'name': branch_info.get('branch', 'unknown'),
                    'default': branch_info.get('default', False),
                    'protected': branch_info.get('protected', False),
                    'last_commit_date': branch_info.get('last_commit_date'),
                    'days_since_last_commit': branch_info.get('days_since_last_commit', 0),
                    'status': branch_info.get('status', 'DESCONOCIDO'),
                }
                
                # Contar ramas inactivas
                if branch_info.get('status') == 'INACTIVA':
                    projects_dict[project_name]['inactive_count'] += 1
                
                projects_dict[project_name]['branches'].append(branch)
            
            analysis_data["projects"] = list(projects_dict.values())
            analysis_data["analysis"]["total_projects"] = len(projects_dict)
            analysis_data["analysis"]["total_branches"] = len(branches_data)
            
        except Exception as e:
            logger.error(f"Error reading inventory file: {e}")
    
    # Leer versiones y releases
    versions_file = output_path / "catalogo_versiones.json"
    if versions_file.exists():
        try:
            with open(versions_file, 'r', encoding='utf-8') as f:
                versions_data = json.load(f)
                # Agregar tags y releases a proyectos
                if isinstance(versions_data, dict):
                    tags = versions_data.get('tags', [])
                    releases = versions_data.get('releases', [])
                    analysis_data["analysis"]["total_tags"] = len(tags)
                    analysis_data["analysis"]["total_releases"] = len(releases)
        except Exception as e:
            logger.error(f"Error reading versions file: {e}")
    
    # Leer reporte de mantenimiento
    maintenance_file = output_path / "reporte_mantenimiento_versiones.json"
    if maintenance_file.exists():
        try:
            with open(maintenance_file, 'r', encoding='utf-8') as f:
                maintenance_data = json.load(f)
                analysis_data["maintenance_report"] = maintenance_data
                
                # Agregar estadísticas al análisis
                ramas_obsoletas = maintenance_data.get('ramas_obsoletas', [])
                analysis_data["analysis"]["total_inactive_branches"] = len(ramas_obsoletas)
                analysis_data["inactive_branches"] = ramas_obsoletas
                
                tags_obsoletos = maintenance_data.get('tags_obsoletos', [])
                analysis_data["analysis"]["total_obsolete_tags"] = len(tags_obsoletos)
                
                artifacts_expiring = maintenance_data.get('artefactos_por_expirar', [])
                analysis_data["analysis"]["artifacts_expiring_soon"] = len(artifacts_expiring)
                
                artifacts_expired = maintenance_data.get('artefactos_expirados', [])
                analysis_data["analysis"]["artifacts_expired"] = len(artifacts_expired)
        except Exception as e:
            logger.error(f"Error reading maintenance file: {e}")
    
    # Leer catálogo de artefactos si existe
    artifacts_file = output_path / "catalogo_artefactos.json"
    if artifacts_file.exists():
        try:
            with open(artifacts_file, 'r', encoding='utf-8') as f:
                artifacts_data = json.load(f)
                analysis_data["artifacts_catalog"] = artifacts_data
        except Exception as e:
            logger.error(f"Error reading artifacts file: {e}")
    
    return analysis_data

# ──────────────────────────────────────────────────────────────────────────────
# MODELADO
# ──────────────────────────────────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    """Parámetros para lanzar el análisis"""
    # destino (para RepositoryAgent)
    project_path: Optional[str] = Field(default=None, description="path del proyecto o repo")
    auto_discover_groups: bool = Field(default=True, description="auto-descubrir grupos/orgs")
    # overrides opcionales
    active_days: int = Field(default=30)
    stale_days: int = Field(default=90)
    artifact_days_soon: int = Field(default=7)
    max_pipelines: int = Field(default=50)
    output_dir: Optional[str] = Field(default=None, description="directorio de salida (opcional)")
    analysis_mode: str = Field(default="basic", description="basic|intelligent")
    # opcional: permitir override de credenciales (si no, usa .env)
    repository_url: Optional[str] = None
    token: Optional[str] = None

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    message: str
    created_at: str
    updated_at: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# ──────────────────────────────────────────────────────────────────────────────
# STARTUP: cargar .env
# ──────────────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def _load_env():
    env_path = BASE_DIR / ".env"
    load_dotenv(env_path)
    logger.info(f"✅ .env cargado desde: {env_path}")

# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/api/v1")
def root():
    return {"message": "GitLab Agent API", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "healthy", "time": datetime.now().isoformat()}

@app.post("/api/v1/analyze")
def analyze(req: AnalyzeRequest, background: BackgroundTasks):
    """
    Lanza el análisis en background.
    Soporta GitLab y GitHub - auto-detecta por URL.
    Credenciales: por .env (REPOSITORY_URL, TOKEN) o en el body.
    """
    # credenciales
    repository_url = req.repository_url or os.getenv("REPOSITORY_URL") or os.getenv("GITLAB_URL", "https://gitlab.com")
    token = req.token or os.getenv("TOKEN") or os.getenv("GITLAB_TOKEN")

    if not token:
        raise HTTPException(status_code=401, detail="TOKEN no configurado (env o body)")

    # Detectar plataforma
    platform = PlatformDetector.detect_platform(repository_url)
    if platform.value == "unknown":
        raise HTTPException(status_code=400, detail=f"Plataforma desconocida: {repository_url}")

    # Validar parámetros: si no es auto_discover, debe tener project_path
    if not req.auto_discover_groups and not req.project_path:
        raise HTTPException(
            status_code=400, 
            detail="Debe especificar 'project_path' cuando 'auto_discover_groups' es false"
        )

    # output
    job_id = create_job()
    update_job(job_id, platform=platform.value)
    out_dir = req.output_dir or str(OUTPUTS_DIR / job_id)

    # AnalysisMode
    mode = AnalysisMode.INTELLIGENT if req.analysis_mode.lower() == "intelligent" else AnalysisMode.BASIC

    # lanzar tarea
    background.add_task(
        _run_analysis_task,
        job_id=job_id,
        repository_url=repository_url,
        token=token,
        project_path=req.project_path,
        auto_discover_groups=req.auto_discover_groups,
        active_days=req.active_days,
        stale_days=req.stale_days,
        artifact_days_soon=req.artifact_days_soon,
        max_pipelines=req.max_pipelines,
        output_dir=out_dir,
        analysis_mode=mode,
    )

    return {"job_id": job_id, "status": "processing", "message": "Análisis iniciado", "platform": platform.value}

@app.get("/api/v1/jobs/{job_id}")
def job_status(job_id: str):
    logger.info(f"🔎 job_status solicitado para {job_id}")
    job = get_job(job_id)
    if job is None:
        # Intentar cargar job.json persistido
        jdir = OUTPUTS_DIR / job_id
        jfile = jdir / "job.json"
        if jfile.exists():
            try:
                import json
                with open(jfile, "r", encoding="utf-8") as f:
                    job = json.load(f)
                # Rehidratar en memoria
                with jobs_lock:
                    jobs_store[job_id] = job
                logger.info(f"♻️ Job {job_id} rehidratado desde disco con estado {job.get('status')}")
            except Exception as e:
                logger.error(f"Error leyendo job.json de {job_id}: {e}")
        if job is None:
            # Si existe directorio de salida intentar generar respuesta final
            output_dir = str(OUTPUTS_DIR / job_id)
            if Path(output_dir).exists():
                analysis_data = load_analysis_data(output_dir)
                if analysis_data:
                    job = {
                        "job_id": job_id,
                        "status": "completed",
                        "progress": 1.0,
                        "message": "Análisis completado (recuperado)",
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat(),
                        "result": {"output_dir": output_dir, "success": True},
                        "error": None,
                        "platform": "unknown",
                        "analysis_data": analysis_data,
                    }
                    return job
            raise HTTPException(status_code=404, detail="Job no encontrado")
    
    # Si el job está completado, cargar los datos del análisis
    result_info = job.get("result") or {}
    output_dir = result_info.get("output_dir")
    if output_dir and Path(output_dir).exists():
        analysis_data = load_analysis_data(output_dir)
        if analysis_data:
            job["analysis_data"] = analysis_data
    
    return job

@app.get("/api/v1/jobs/{job_id}/analysis")
def job_analysis(job_id: str):
    """Retorna solo analysis_data y estado."""
    j = job_status(job_id)
    return {
        "job_id": j["job_id"],
        "status": j["status"],
        "platform": j.get("platform"),
        "analysis_data": j.get("analysis_data")
    }

@app.get("/api/v1/jobs/{job_id}/insights")
def job_insights(job_id: str):
    """
    Retorna insights y recomendaciones generados por LLM
    - Executive summary
    - Top risks
    - Immediate actions
    - Health score
    """
    if not LLM_AVAILABLE:
        raise HTTPException(status_code=503, detail="LLM no disponible")
    
    j = job_status(job_id)
    analysis_data = j.get("analysis_data")
    
    if not analysis_data:
        raise HTTPException(status_code=404, detail="Sin datos de análisis")
    
    try:
        analyzer = get_llm_analyzer()
        summary = analyzer.generate_executive_summary(analysis_data)
        return {
            "job_id": job_id,
            "status": j["status"],
            "insights": summary
        }
    except Exception as e:
        logger.error(f"Error generando insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/jobs/{job_id}/recommendations")
def job_recommendations(job_id: str):
    """
    Retorna plan de limpieza priorizado con recomendaciones
    - Fase 1: Eliminar ahora
    - Fase 2: Revisar primero
    - Fase 3: Archivar
    """
    if not LLM_AVAILABLE:
        raise HTTPException(status_code=503, detail="LLM no disponible")
    
    j = job_status(job_id)
    analysis_data = j.get("analysis_data")
    
    if not analysis_data:
        raise HTTPException(status_code=404, detail="Sin datos de análisis")
    
    try:
        analyzer = get_llm_analyzer()
        plan = analyzer.generate_cleanup_recommendations(analysis_data)
        return {
            "job_id": job_id,
            "status": j["status"],
            "cleanup_plan": plan
        }
    except Exception as e:
        logger.error(f"Error generando recomendaciones: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/jobs/{job_id}/branch/{project_name}/{branch_name}/analysis")
def branch_health_analysis(job_id: str, project_name: str, branch_name: str):
    """
    Analiza la salud de una rama individual
    Retorna: riesgo, justificación, acciones recomendadas
    """
    if not LLM_AVAILABLE:
        raise HTTPException(status_code=503, detail="LLM no disponible")
    
    j = job_status(job_id)
    analysis_data = j.get("analysis_data")
    
    if not analysis_data:
        raise HTTPException(status_code=404, detail="Sin datos de análisis")
    
    # Encontrar la rama
    projects = analysis_data.get("projects", [])
    branch = None
    for project in projects:
        if project.get("name") == project_name:
            for b in project.get("branches", []):
                if b.get("name") == branch_name:
                    branch = b
                    break
            break
    
    if not branch:
        raise HTTPException(status_code=404, detail="Rama no encontrada")
    
    try:
        analyzer = get_llm_analyzer()
        analysis = analyzer.analyze_branch_health(branch, project_name)
        return {
            "job_id": job_id,
            "project": project_name,
            "branch": branch_name,
            "analysis": analysis
        }
    except Exception as e:
        logger.error(f"Error analizando rama: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/outputs")
def list_outputs():
    """Lista directorios de outputs existentes (histórico)."""
    items = []
    for d in OUTPUTS_DIR.iterdir():
        if d.is_dir():
            job_id = d.name
            jfile = d / "job.json"
            updated = None
            if jfile.exists():
                updated = datetime.fromtimestamp(jfile.stat().st_mtime).isoformat()
            items.append({"job_id": job_id, "updated_at": updated})
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return {"outputs": items, "count": len(items)}

@app.get("/api/v1/jobs")
def list_jobs():
    """Lista todos los jobs en memoria, intenta rehidratar si está vacío."""
    if not jobs_store:
        _rehydrate_jobs_from_disk()
    with jobs_lock:
        return {"jobs": list(jobs_store.values()), "count": len(jobs_store)}

@app.post("/api/v1/jobs/rehydrate")
def force_rehydrate():
    _rehydrate_jobs_from_disk()
    with jobs_lock:
        return {"jobs": list(jobs_store.values()), "count": len(jobs_store)}

@app.get("/api/v1/download/{job_id}")
def download(job_id: str):
    """Comprime y descarga el directorio de salida del job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    result = job.get("result") or {}
    output_dir = result.get("output_dir")
    if not output_dir or not Path(output_dir).exists():
        raise HTTPException(status_code=404, detail="Archivos de salida no encontrados")

    zip_path = Path(output_dir).with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(Path(output_dir)), "zip", Path(output_dir))

    return FileResponse(
        path=str(zip_path),
        filename=f"{Path(output_dir).name}.zip",
        media_type="application/zip",
    )

# ──────────────────────────────────────────────────────────────────────────────
# WORKER
# ──────────────────────────────────────────────────────────────────────────────
def _run_analysis_task(
    job_id: str,
    repository_url: str,
    token: str,
    project_path: Optional[str],
    auto_discover_groups: bool,
    active_days: int,
    stale_days: int,
    artifact_days_soon: int,
    max_pipelines: int,
    output_dir: str,
    analysis_mode: AnalysisMode,
):
    """Ejecuta el RepositoryAgent y actualiza el estado del job."""
    try:
        # Detectar plataforma
        platform = PlatformDetector.detect_platform(repository_url)
        platform_str = platform.value if hasattr(platform, 'value') else str(platform)
        
        update_job(job_id, status="processing", progress=0.05, message="Inicializando agente…", platform=platform_str)

        agent = RepositoryAgent(
            repository_url=repository_url,
            token=token,
            project_path=project_path,
            auto_discover_groups=auto_discover_groups,
            active_days=active_days,
            stale_days=stale_days,
            artifact_days_soon=artifact_days_soon,
            max_pipelines=max_pipelines,
            output_dir=output_dir,
            llm_client=None,  # conecta tu LLM si quieres usar modo intelligent
            analysis_mode=analysis_mode,
        )

        update_job(job_id, progress=0.15, message="Conectando y cargando proyectos…")
        result = agent.run()  # ejecuta workflow LangGraph internamente

        if not result.get("success"):
            update_job(
                job_id,
                status="failed",
                progress=0.0,
                error=result.get("error", "Error desconocido"),
                message=f"Falló: {result.get('error')}",
                result={"output_dir": output_dir},
            )
            return

        # éxito
        update_job(
            job_id,
            status="completed",
            progress=1.0,
            message="Análisis completado",
            result={
                "output_dir": output_dir,
                "success": True,
                "state_keys": list((result.get("state") or {}).keys()),
            },
        )
        logger.info(f"✅ Job {job_id} completado. Resultados en: {output_dir}")

    except Exception as e:
        logger.exception(f"❌ Error en job {job_id}: {e}")
        update_job(
            job_id,
            status="failed",
            progress=0.0,
            error=str(e),
            message=f"Error: {e}",
            result={"output_dir": output_dir},
        )

# ──────────────────────────────────────────────────────────────────────────────
# MONTAR ARCHIVOS ESTÁTICOS DEL FRONTEND (después de todas las rutas API)
# ──────────────────────────────────────────────────────────────────────────────
if WEB_DIR.exists():
    # Montamos en /app para no interferir con /health y /api/v1/*
    app.mount("/app", StaticFiles(directory=str(WEB_DIR), html=True), name="static")
    logger.info(f"✅ Web estático montado en /app desde {WEB_DIR}")
    @app.get("/")
    def serve_root():
        return FileResponse(WEB_DIR / "index.html")
    # Fallback para servir assets si el navegador resuelve relativo a /
    @app.get("/style.css")
    def style_root():
        return FileResponse(WEB_DIR / "style.css")
    @app.get("/app.js")
    def script_root():
        return FileResponse(WEB_DIR / "app.js")

# ──────────────────────────────────────────────────────────────────────────────
# RUN (dev)
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=True, log_level="info")
