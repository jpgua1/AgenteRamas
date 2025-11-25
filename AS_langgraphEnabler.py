"""
GitLab/GitHub Repository Agent - LangGraph Version (msgpack-safe)
================================================================
Agente inteligente para análisis de repositorios GitLab y GitHub usando LangGraph.
- Auto-detecta todos los grupos en GitLab sin necesidad de pasarlos
- Soporta tanto GitLab como GitHub según la URL
- State solo guarda tipos JSON-serializables (dict/list/str/int/bool/float/None)
- No guarda objetos Project de python-gitlab ni dataclasses en el state
"""

import os
import sys
import json
import re
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Annotated, TypedDict
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv
import gitlab
from urllib.parse import urlparse

# LangGraph imports
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages

# GitHub imports (opcional)
try:
    from github import Github
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False
    logging.warning("PyGithub no disponible. Modo GitLab únicamente.")

# Azure DevOps imports (opcional)
try:
    from azure.devops.connection import Connection
    from azure.devops.v7_0.git.models import GitRepository
    from msrest.authentication import BasicAuthentication
    AZURE_DEVOPS_AVAILABLE = True
except ImportError:
    AZURE_DEVOPS_AVAILABLE = False
    logging.warning("Azure DevOps SDK no disponible.")

# Azure Provider (opcional para análisis inteligente)
try:
    from AzureProvider import get_azure_provider
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    logging.warning("AzureProvider no disponible. Modo análisis básico activado.")

# ========================================================================
# CONFIGURACIÓN DE LOGGING
# ========================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
for noisy in ["azure", "httpx", "gitlab", "urllib3"]:
    logging.getLogger(noisy).setLevel(logging.WARNING)

# ========================================================================
# CONFIGURACIÓN Y ENUMS
# ========================================================================

class AnalysisMode(str, Enum):
    BASIC = "basic"
    INTELLIGENT = "intelligent"

class BranchStatus(str, Enum):
    ACTIVE = "ACTIVA"
    LATENT = "LATENTE"
    INACTIVE = "INACTIVA"

class RepositoryPlatform(str, Enum):
    GITLAB = "gitlab"
    GITHUB = "github"
    AZURE_DEVOPS = "azure_devops"
    UNKNOWN = "unknown"

# ========================================================================
# DATACLASSES (para uso interno, nunca se guardan en state)
# ========================================================================

@dataclass
class BranchInfo:
    project_id: int
    project: str
    branch: str
    default: bool
    protected: bool
    last_commit_id: Optional[str]
    last_commit_date: Optional[str]
    days_since_last_commit: Optional[int]
    status: str

@dataclass
class TagInfo:
    project_id: int
    project: str
    tag: str
    is_semver: bool
    commit_id: Optional[str]
    date: Optional[str]
    days_since: Optional[int]

@dataclass
class ReleaseInfo:
    project_id: int
    project: str
    name: Optional[str]
    tag_name: Optional[str]
    created_at: Optional[str]
    description_short: str

@dataclass
class ArtifactInfo:
    project_id: int
    project: str
    pipeline_id: int
    pipeline_status: Optional[str]
    job_id: int
    job_name: Optional[str]
    artifact_filename: str
    artifact_size_bytes: Optional[int]
    artifact_expire_at: Optional[str]
    artifact_days_to_expire: Optional[int]

# ========================================================================
# LANGGRAPH STATE (solo tipos serializables)
# ========================================================================

class GitLabAgentState(TypedDict):
    # Configuración
    config: Dict[str, Any]

    # Proyectos (solo ids y metadatos simples)
    project_ids: List[int]
    projects_meta: List[Dict[str, Any]]

    # Datos recolectados (dicts, no dataclasses)
    branches: List[Dict[str, Any]]
    tags: List[Dict[str, Any]]
    releases: List[Dict[str, Any]]
    artifacts: List[Dict[str, Any]]

    # Reportes (dict)
    maintenance_report: Optional[Dict[str, Any]]
    insights: Optional[str]

    # Control de flujo
    status: str
    error: Optional[str]
    messages: Annotated[list, add_messages]

# ========================================================================
# UTILIDADES
# ========================================================================

class PlatformDetector:
    """Detecta y parsea URLs de GitLab, GitHub y Azure DevOps"""
    
    @staticmethod
    def detect_platform(url: str) -> RepositoryPlatform:
        """Detecta si una URL es de GitLab, GitHub, Azure DevOps u otra plataforma"""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or parsed.netloc
            
            if "github.com" in hostname:
                return RepositoryPlatform.GITHUB
            elif "dev.azure.com" in hostname or "visualstudio.com" in hostname:
                return RepositoryPlatform.AZURE_DEVOPS
            elif "gitlab" in hostname or "git" in hostname.lower():
                # Si contiene "gitlab" o "git" en el hostname, asumir que es GitLab
                return RepositoryPlatform.GITLAB
            else:
                # Por defecto, asumir GitLab para cualquier URL no identificada
                return RepositoryPlatform.GITLAB
        except Exception:
            return RepositoryPlatform.GITLAB
    
    @staticmethod
    def get_api_url(url: str) -> str:
        """Extrae la URL base de la API"""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or parsed.netloc
            
            if "github.com" in hostname:
                return "https://api.github.com"
            elif "dev.azure.com" in hostname or "visualstudio.com" in hostname:
                # Azure DevOps API
                return "https://dev.azure.com"
            elif "gitlab" in hostname:
                # Para GitLab, usa la URL base del servidor
                scheme = parsed.scheme or "https"
                return f"{scheme}://{hostname}"
            else:
                return url
        except Exception:
            return url

class GitLabUtils:
    SEMVER_RE = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].*)?$")

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def parse_iso(dt_str: str) -> datetime:
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            # fallback común en GitLab
            from datetime import datetime as dt
            return dt.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)

    @staticmethod
    def days_ago(dt: datetime) -> int:
        return (GitLabUtils.utcnow() - dt).days

    @staticmethod
    def is_semver(tag_name: str) -> bool:
        return GitLabUtils.SEMVER_RE.match(tag_name) is not None

    @staticmethod
    def save_json(obj: Any, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    @staticmethod
    def gl_list_all(func, **kwargs) -> List:
        page = 1
        per_page = kwargs.pop("per_page", 100)
        acc = []
        while True:
            items = func(page=page, per_page=per_page, **kwargs)
            if not items:
                break
            acc.extend(items)
            if len(items) < per_page:
                break
            page += 1
        return acc

# ========================================================================
# COLECTORES DE DATOS (devuelven dataclasses; se convierten a dict antes de guardar)
# ========================================================================

class BranchCollector:
    def __init__(self, active_days: int = 30, stale_days: int = 90):
        self.active_days = active_days
        self.stale_days = stale_days

    def collect(self, project) -> List[BranchInfo]:
        try:
            branches = GitLabUtils.gl_list_all(project.branches.list)
        except gitlab.exceptions.GitlabListError as e:
            logger.warning(f"No se pudieron listar ramas del proyecto {project.path_with_namespace}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error listando ramas: {e}")
            return []

        result = []
        for b in branches:
            try:
                commit = b.commit or {}
                committed_date = commit.get("committed_date") or commit.get("created_at")
                dt = GitLabUtils.parse_iso(committed_date) if committed_date else None
                d_ago = GitLabUtils.days_ago(dt) if dt else None

                if d_ago is not None and d_ago <= self.active_days:
                    status = BranchStatus.ACTIVE
                elif d_ago is not None and d_ago > self.stale_days:
                    status = BranchStatus.INACTIVE
                else:
                    status = BranchStatus.LATENT

                result.append(BranchInfo(
                    project_id=project.id,
                    project=project.path_with_namespace,
                    branch=b.name,
                    default=getattr(b, "default", False),
                    protected=getattr(b, "protected", False),
                    last_commit_id=commit.get("id") if commit else None,
                    last_commit_date=dt.isoformat() if dt else None,
                    days_since_last_commit=d_ago,
                    status=status.value
                ))
            except Exception as e:
                logger.warning(f"Error procesando rama {getattr(b, 'name', 'unknown')}: {e}")
                continue

        return result

class TagCollector:
    def collect_tags(self, project) -> List[TagInfo]:
        try:
            tags = GitLabUtils.gl_list_all(project.tags.list)
        except gitlab.exceptions.GitlabListError as e:
            logger.warning(f"No se pudieron listar tags: {e}")
            return []
        except Exception as e:
            logger.error(f"Error listando tags: {e}")
            return []

        result = []
        for t in tags:
            try:
                commit = getattr(t, "commit", {}) or {}
                date = commit.get("committed_date") or commit.get("created_at")
                dt = GitLabUtils.parse_iso(date) if date else None

                result.append(TagInfo(
                    project_id=project.id,
                    project=project.path_with_namespace,
                    tag=t.name,
                    is_semver=GitLabUtils.is_semver(t.name),
                    commit_id=commit.get("id"),
                    date=dt.isoformat() if dt else None,
                    days_since=GitLabUtils.days_ago(dt) if dt else None
                ))
            except Exception as e:
                logger.warning(f"Error procesando tag {getattr(t, 'name', 'unknown')}: {e}")
                continue

        return result

    def collect_releases(self, project) -> List[ReleaseInfo]:
        try:
            releases = GitLabUtils.gl_list_all(project.releases.list)
        except gitlab.exceptions.GitlabListError as e:
            logger.warning(f"No se pudieron listar releases: {e}")
            return []
        except Exception as e:
            logger.error(f"Error listando releases: {e}")
            return []

        result = []
        for r in releases:
            try:
                created = getattr(r, "created_at", None)
                dt = GitLabUtils.parse_iso(created) if created else None

                result.append(ReleaseInfo(
                    project_id=project.id,
                    project=project.path_with_namespace,
                    name=getattr(r, "name", None),
                    tag_name=getattr(r, "tag_name", None),
                    created_at=dt.isoformat() if dt else None,
                    description_short=(getattr(r, "description", None) or "")[:140]
                ))
            except Exception as e:
                logger.warning(f"Error procesando release: {e}")
                continue

        return result

class ArtifactCollector:
    def __init__(self, max_pipelines: int = 50):
        self.max_pipelines = max_pipelines

    def collect(self, project) -> List[ArtifactInfo]:
        try:
            pipelines = GitLabUtils.gl_list_all(project.pipelines.list)[:self.max_pipelines]
        except gitlab.exceptions.GitlabListError as e:
            # Silenciar 403 como debug para no inundar logs
            if '403' in str(e):
                logger.debug(f"Pipelines no accesibles (403): {e}")
                return []
            logger.warning(f"No se pudieron listar pipelines: {e}")
            return []
        except Exception as e:
            logger.error(f"Error listando pipelines: {e}")
            return []

        result = []
        for p in pipelines:
            try:
                jobs = GitLabUtils.gl_list_all(project.jobs.list, pipeline_id=p.id)
                for j in jobs:
                    af = (j.attributes or {}).get("artifacts_file") or {}
                    fn = af.get("filename")
                    sz = af.get("size")
                    exp = (j.attributes or {}).get("artifacts_expire_at")

                    if fn:
                        exp_dt = GitLabUtils.parse_iso(exp) if exp else None
                        days_to_expire = None
                        if exp_dt:
                            days_to_expire = (exp_dt - GitLabUtils.utcnow()).days

                        result.append(ArtifactInfo(
                            project_id=project.id,
                            project=project.path_with_namespace,
                            pipeline_id=p.id,
                            pipeline_status=getattr(p, "status", None),
                            job_id=j.id,
                            job_name=getattr(j, "name", None),
                            artifact_filename=fn,
                            artifact_size_bytes=sz,
                            artifact_expire_at=exp_dt.isoformat() if exp_dt else None,
                            artifact_days_to_expire=days_to_expire
                        ))
            except Exception as e:
                logger.warning(f"Error procesando pipeline {p.id}: {e}")
                continue

        return result

# ========================================================================
# GENERADOR DE REPORTES (trabaja con dicts)
# ========================================================================

class ReportGenerator:
    def __init__(self, stale_days: int = 90, artifact_days_soon: int = 7):
        self.stale_days = stale_days
        self.artifact_days_soon = artifact_days_soon

    def generate(self,
                 branches: List[Dict[str, Any]],
                 tags: List[Dict[str, Any]],
                 artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:

        ramas_obsoletas = [b for b in branches if b.get("status") == BranchStatus.INACTIVE.value]
        tags_no_semver  = [t for t in tags if not t.get("is_semver", False)]
        tags_obsoletos  = [t for t in tags if (t.get("days_since") is not None and t["days_since"] > self.stale_days)]

        artefactos_por_expirar: List[Dict[str, Any]] = []
        artefactos_expirados: List[Dict[str, Any]] = []
        for a in artifacts:
            dte = a.get("artifact_days_to_expire")
            if dte is None:
                continue
            if 0 <= dte <= self.artifact_days_soon:
                artefactos_por_expirar.append(a)
            elif dte < 0:
                artefactos_expirados.append(a)

        return {
            "ramas_obsoletas": ramas_obsoletas,
            "tags_no_semver": tags_no_semver,
            "tags_obsoletos": tags_obsoletos,
            "artefactos_por_expirar": artefactos_por_expirar,
            "artefactos_expirados": artefactos_expirados,
        }

# ========================================================================
# ANALIZADOR INTELIGENTE (usa state serializable)
# ========================================================================

class IntelligentAnalyzer:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def analyze(self, state: GitLabAgentState) -> str:
        if not self.llm_client:
            return "Análisis inteligente no disponible (LLM no configurado)"

        try:
            return self._basic_analysis(state)
        except Exception as e:
            logger.error(f"Error en análisis inteligente: {e}")
            return f"Error en análisis: {str(e)}"

    def _prepare_summary(self, state: GitLabAgentState) -> str:
        branches = state.get("branches", [])
        tags = state.get("tags", [])
        artifacts = state.get("artifacts", [])
        maintenance = state.get("maintenance_report")

        summary = f"""
DATOS DEL REPOSITORIO:
- Total proyectos: {len(state.get('project_ids', []))}
- Total ramas: {len(branches)}
- Total tags: {len(tags)}
- Total artefactos: {len(artifacts)}

ESTADO DE RAMAS:
- Activas: {len([b for b in branches if b.get('status') == 'ACTIVA'])}
- Latentes: {len([b for b in branches if b.get('status') == 'LATENTE'])}
- Inactivas: {len([b for b in branches if b.get('status') == 'INACTIVA'])}

VERSIONADO:
- Tags semver: {len([t for t in tags if t.get('is_semver')])}
- Tags no semver: {len([t for t in tags if not t.get('is_semver')])}

ALERTAS DE MANTENIMIENTO:
"""
        if maintenance:
            summary += f"""
- Ramas obsoletas: {len(maintenance.get('ramas_obsoletas', []))}
- Tags obsoletos: {len(maintenance.get('tags_obsoletos', []))}
- Artefactos por expirar: {len(maintenance.get('artefactos_por_expirar', []))}
- Artefactos expirados: {len(maintenance.get('artefactos_expirados', []))}
"""
        return summary

    def _basic_analysis(self, state: GitLabAgentState) -> str:
        branches = state.get("branches", [])
        maintenance = state.get("maintenance_report")

        insights = []
        inactive_count = len([b for b in branches if b.get("status") == 'INACTIVA'])
        if inactive_count > 10:
            insights.append(f"⚠️ {inactive_count} ramas inactivas detectadas - considerar limpieza")

        if maintenance:
            if len(maintenance.get("tags_no_semver", [])) > 5:
                insights.append(f"💡 {len(maintenance.get('tags_no_semver', []))} tags sin semver - estandarizar versionado")
            if len(maintenance.get("artefactos_por_expirar", [])) > 0:
                insights.append(f"⏰ {len(maintenance.get('artefactos_por_expirar', []))} artefactos próximos a expirar")

        return "\n".join(insights) if insights else "✅ No se detectaron problemas críticos"

# ========================================================================
# GITLAB AGENT - ORQUESTADOR PRINCIPAL
# ========================================================================

class RepositoryAgent:
    """Agente universal para GitLab y GitHub"""
    
    def __init__(self,
                 repository_url: str,
                 token: str,
                 project_path: Optional[str] = None,
                 auto_discover_groups: bool = True,
                 active_days: int = 30,
                 stale_days: int = 90,
                 artifact_days_soon: int = 7,
                 max_pipelines: int = 50,
                 output_dir: str = "./out",
                 llm_client=None,
                 analysis_mode: AnalysisMode = AnalysisMode.BASIC):

        self.repository_url = repository_url
        self.token = token
        self.project_path = project_path
        self.auto_discover_groups = auto_discover_groups
        self.active_days = active_days
        self.stale_days = stale_days
        self.artifact_days_soon = artifact_days_soon
        self.max_pipelines = max_pipelines
        self.output_dir = output_dir
        self.llm_client = llm_client
        self.analysis_mode = analysis_mode

        # Detectar plataforma
        self.platform = PlatformDetector.detect_platform(repository_url)
        self.api_url = PlatformDetector.get_api_url(repository_url)
        
        logger.info(f"🔍 Plataforma detectada: {self.platform.value}")
        logger.info(f"📍 API URL: {self.api_url}")

        os.makedirs(self.output_dir, exist_ok=True)
        self._validate_config()

        self.branch_collector = BranchCollector(active_days, stale_days)
        self.tag_collector = TagCollector()
        self.artifact_collector = ArtifactCollector(max_pipelines)
        self.report_generator = ReportGenerator(stale_days, artifact_days_soon)
        self.intelligent_analyzer = IntelligentAnalyzer(llm_client)

        self.gl = None
        self.gh = None
        self.azure = None
        self._project_cache: Dict[int, Any] = {}
        self.discovered_groups: List[str] = []

        self.checkpointer = MemorySaver()
        self.workflow = self._build_workflow()

        logger.info("RepositoryAgent inicializado correctamente")

    def _validate_config(self):
        if not self.token or not self.repository_url:
            raise ValueError("token y repository_url son requeridos")
        
        if self.platform == RepositoryPlatform.UNKNOWN:
            raise ValueError(f"Plataforma desconocida: {self.repository_url}")

    def _connect_gitlab(self):
        """Conecta con GitLab"""
        try:
            self.gl = gitlab.Gitlab(self.api_url, private_token=self.token)
            self.gl.auth()
            logger.info("✅ Conectado a GitLab")
            return True
        except Exception as e:
            logger.error(f"❌ Error conectando a GitLab: {e}")
            return False

    def _connect_github(self):
        """Conecta con GitHub"""
        if not GITHUB_AVAILABLE:
            logger.error("PyGithub no disponible. Instala: pip install PyGithub")
            return False
        
        try:
            self.gh = Github(self.token)
            # Test de conexión
            self.gh.get_user().login
            logger.info("✅ Conectado a GitHub")
            return True
        except Exception as e:
            logger.error(f"❌ Error conectando a GitHub: {e}")
            return False

    def _connect_azure_devops(self):
        """Conecta con Azure DevOps"""
        if not AZURE_DEVOPS_AVAILABLE:
            logger.error("Azure DevOps SDK no disponible. Instala: pip install azure-devops")
            return False
        
        try:
            # Azure DevOps requiere formato especial para la URL
            # Formato: https://dev.azure.com/{organization}
            parsed = urlparse(self.repository_url)
            
            # Extraer organización de la URL
            # Si es https://dev.azure.com, el project_path debe ser "org/project"
            # Si es formato personalizado, usar el dominio como org
            if "dev.azure.com" in parsed.netloc:
                # Formato estándar: https://dev.azure.com
                if self.project_path:
                    org_name = self.project_path.split('/')[0]
                else:
                    # Intentar extraer del path
                    org_name = parsed.path.strip('/').split('/')[0] if parsed.path else "DefaultOrg"
            else:
                # Formato personalizado: dominio personalizado
                org_name = parsed.netloc.split('.')[0]
            
            # Crear conexión con autenticación PAT (Personal Access Token)
            credentials = BasicAuthentication('', self.token)
            organization_url = f"https://dev.azure.com/{org_name}"
            self.azure = Connection(base_url=organization_url, creds=credentials)
            
            # Test de conexión
            self.azure.clients.get_core_client().get_projects()
            logger.info("✅ Conectado a Azure DevOps")
            return True
        except Exception as e:
            logger.error(f"❌ Error conectando a Azure DevOps: {e}")
            return False

    def _discover_gitlab_groups(self) -> List[str]:
        """Auto-descubre todos los grupos accesibles en GitLab"""
        if not self.gl:
            return []
        
        try:
            logger.info("🔍 Descubriendo grupos en GitLab...")
            groups = self.gl.groups.list(get_all=True)
            
            # Filtrar solo grupos accesibles
            accessible_groups = []
            for g in groups:
                try:
                    # Intentar acceder al grupo para verificar que sea accesible
                    self.gl.groups.get(g.path)
                    accessible_groups.append(g.path)
                except Exception:
                    # Si no es accesible, ignorar silenciosamente
                    pass
            
            logger.info(f"   ✅ {len(accessible_groups)} grupos accesibles encontrados: {', '.join(accessible_groups[:5])}{'...' if len(accessible_groups) > 5 else ''}")
            return accessible_groups
        except Exception as e:
            logger.warning(f"⚠️ Error descubriendo grupos: {e}")
            return []

    def _discover_github_orgs(self) -> List[str]:
        """Auto-descubre todas las organizaciones y repositorios personales en GitHub"""
        if not self.gh:
            return []
        
        try:
            logger.info("🔍 Descubriendo organizaciones y repositorios en GitHub...")
            user = self.gh.get_user()
            
            # Obtener organizaciones
            orgs = [org.login for org in user.get_orgs()]
            
            # Incluir el usuario personal como "organización"
            personal_login = user.login
            all_orgs = [personal_login] + orgs
            
            logger.info(f"   ✅ {len(all_orgs)} orgs/usuarios encontrados: {', '.join(all_orgs[:5])}{'...' if len(all_orgs) > 5 else ''}")
            return all_orgs
        except Exception as e:
            logger.warning(f"⚠️ Error descubriendo organizaciones: {e}")
            return []

    def _discover_azure_projects(self) -> List[str]:
        """Auto-descubre todos los proyectos accesibles en Azure DevOps"""
        if not self.azure:
            return []
        
        try:
            logger.info("🔍 Descubriendo proyectos en Azure DevOps...")
            core_client = self.azure.clients.get_core_client()
            projects = core_client.get_projects()
            
            project_names = [p.name for p in projects.value]
            logger.info(f"   ✅ {len(project_names)} proyectos encontrados: {', '.join(project_names[:5])}{'...' if len(project_names) > 5 else ''}")
            return project_names
        except Exception as e:
            logger.warning(f"⚠️ Error descubriendo proyectos: {e}")
            return []

    def _get_project(self, pid: int):
        if pid not in self._project_cache:
            self._project_cache[pid] = self.gl.projects.get(pid)
        return self._project_cache[pid]

    def _build_workflow(self) -> StateGraph:
        workflow = StateGraph(GitLabAgentState)

        def init_node(state: GitLabAgentState) -> GitLabAgentState:
            platform_name = "Repositorio" if self.platform == RepositoryPlatform.UNKNOWN else self.platform.value.upper()
            logger.info(f"🚀 Inicializando agente {platform_name}...")
            state["status"] = "initialized"
            state.setdefault("project_ids", [])
            state.setdefault("projects_meta", [])
            state.setdefault("branches", [])
            state.setdefault("tags", [])
            state.setdefault("releases", [])
            state.setdefault("artifacts", [])
            state.setdefault("maintenance_report", None)
            state.setdefault("insights", None)
            state.setdefault("error", None)
            state.setdefault("messages", [])
            state["messages"].append({"role": "system", "content": f"Agente {platform_name} inicializado"})
            return state

        def connect_repository_node(state: GitLabAgentState) -> GitLabAgentState:
            logger.info(f"🔌 Conectando a {self.platform.value}...")
            try:
                if self.platform == RepositoryPlatform.GITLAB:
                    success = self._connect_gitlab()
                elif self.platform == RepositoryPlatform.GITHUB:
                    success = self._connect_github()
                elif self.platform == RepositoryPlatform.AZURE_DEVOPS:
                    success = self._connect_azure_devops()
                else:
                    success = False
                
                if success:
                    logger.info(f"✅ Conectado a {self.platform.value}")
                    state["status"] = "connected"
                    state["messages"].append({"role": "system", "content": "Conexión exitosa"})
                else:
                    raise Exception(f"No se pudo conectar a {self.platform.value}")
            except Exception as e:
                error_msg = f"Error conectando a {self.platform.value}: {e}"
                logger.error(error_msg)
                state["status"] = "error"
                state["error"] = error_msg
            return state

        def get_projects_node(state: GitLabAgentState) -> GitLabAgentState:
            logger.info("📦 Obteniendo proyectos...")
            try:
                projects = []
                
                if self.platform == RepositoryPlatform.GITLAB:
                    # Auto-descubrir grupos si no se especificó uno
                    if self.auto_discover_groups and not self.project_path:
                        groups = self._discover_gitlab_groups()
                        accessible_groups = []
                        for group_path in groups:
                            try:
                                group = self.gl.groups.get(group_path)
                                logger.info(f"   📁 Grupo: {group.full_path}")
                                group_projects = GitLabUtils.gl_list_all(group.projects.list)
                                projects.extend(group_projects)
                                accessible_groups.append(group_path)
                            except Exception as e:
                                logger.debug(f"   ⏭️  Saltando grupo inaccesible '{group_path}': {e}")
                                # Continuar sin loguear como warning
                                continue
                        
                        if accessible_groups:
                            logger.info(f"   ✅ {len(accessible_groups)} grupos accesibles: {', '.join(accessible_groups[:3])}{'...' if len(accessible_groups) > 3 else ''}")
                        else:
                            logger.warning(f"   ⚠️ No se encontraron grupos accesibles (se encontraron {len(groups)} pero ninguno es accesible)")
                    elif self.project_path:
                        # Si se especificó un proyecto
                        proj = self.gl.projects.get(self.project_path)
                        projects = [proj]
                        logger.info(f"   📄 Proyecto: {proj.path_with_namespace}")
                    
                    # Resolver proyectos
                    resolved = []
                    for p in projects:
                        try:
                            proj = self.gl.projects.get(p.id if hasattr(p, "id") else p["id"])
                            resolved.append(proj)
                        except Exception as e:
                            logger.warning(f"   Error resolviendo proyecto: {e}")
                            continue
                    
                    state["project_ids"] = [p.id for p in resolved]
                    state["projects_meta"] = [{"id": p.id, "path": p.path_with_namespace} for p in resolved]
                
                elif self.platform == RepositoryPlatform.GITHUB:
                    # GitHub: auto-descubrir organizaciones y usuario personal o usar repositorio específico
                    if self.auto_discover_groups and not self.project_path:
                        orgs = self._discover_github_orgs()
                        for org_name in orgs:
                            try:
                                # Intentar como organización primero
                                try:
                                    org = self.gh.get_organization(org_name)
                                    logger.info(f"   🏢 Organización: {org.login}")
                                    org_repos = org.get_repos()
                                except:
                                    # Si falla, es probablemente el usuario personal
                                    user = self.gh.get_user(org_name)
                                    logger.info(f"   👤 Usuario personal: {user.login}")
                                    org_repos = user.get_repos()
                                
                                for repo in org_repos:
                                    state["project_ids"].append(repo.id)
                                    state["projects_meta"].append({
                                        "id": repo.id,
                                        "path": repo.full_name,
                                        "platform": "github"
                                    })
                            except Exception as e:
                                logger.debug(f"   ⏭️  Saltando {org_name}: {e}")
                                continue
                    elif self.project_path:
                        # Si se especificó un repositorio
                        repo = self.gh.get_repo(self.project_path)
                        state["project_ids"] = [repo.id]
                        state["projects_meta"] = [{
                            "id": repo.id,
                            "path": repo.full_name,
                            "platform": "github"
                        }]
                        logger.info(f"   📄 Repositorio: {repo.full_name}")
                elif self.platform == RepositoryPlatform.AZURE_DEVOPS:
                    # Azure DevOps: auto-descubrir proyectos o usar proyecto específico
                    if self.auto_discover_groups and not self.project_path:
                        project_names = self._discover_azure_projects()
                        for proj_name in project_names:
                            try:
                                git_client = self.azure.clients.get_git_client()
                                repositories = git_client.get_repositories(project=proj_name)
                                logger.info(f"   📁 Proyecto: {proj_name}")
                                
                                for repo in repositories:
                                    state["project_ids"].append(repo.id)
                                    state["projects_meta"].append({
                                        "id": repo.id,
                                        "path": f"{proj_name}/{repo.name}",
                                        "platform": "azure_devops",
                                        "project": proj_name
                                    })
                            except Exception as e:
                                logger.debug(f"   ⏭️  Saltando proyecto {proj_name}: {e}")
                                continue
                    elif self.project_path:
                        # Si se especificó un proyecto/repositorio
                        # Formato: "project_name/repo_name"
                        parts = self.project_path.split('/')
                        proj_name = parts[0]
                        repo_name = parts[1] if len(parts) > 1 else None
                        
                        try:
                            git_client = self.azure.clients.get_git_client()
                            if repo_name:
                                repo = git_client.get_repository(repository_id=repo_name, project=proj_name)
                                state["project_ids"] = [repo.id]
                                state["projects_meta"] = [{
                                    "id": repo.id,
                                    "path": f"{proj_name}/{repo.name}",
                                    "platform": "azure_devops",
                                    "project": proj_name
                                }]
                                logger.info(f"   📄 Repositorio: {proj_name}/{repo.name}")
                            else:
                                # Si solo hay proyecto, obtener todos sus repos
                                repositories = git_client.get_repositories(project=proj_name)
                                for repo in repositories:
                                    state["project_ids"].append(repo.id)
                                    state["projects_meta"].append({
                                        "id": repo.id,
                                        "path": f"{proj_name}/{repo.name}",
                                        "platform": "azure_devops",
                                        "project": proj_name
                                    })
                        except Exception as e:
                            logger.error(f"   Error obteniendo repositorio: {e}")
                
                state["status"] = "projects_loaded"
                state["messages"].append({"role": "system", "content": f"{len(state['project_ids'])} proyectos cargados"})
                logger.info(f"✅ {len(state['project_ids'])} proyectos cargados")

            except Exception as e:
                error_msg = f"Error obteniendo proyectos: {e}"
                logger.error(error_msg)
                state["status"] = "error"
                state["error"] = error_msg

            return state

        def analyze_branches_node(state: GitLabAgentState) -> GitLabAgentState:
            logger.info("🌿 Analizando ramas...")
            all_branches_dicts: List[Dict[str, Any]] = []

            for idx, (pid, meta) in enumerate(zip(state["project_ids"], state["projects_meta"])):
                try:
                    if self.platform == RepositoryPlatform.GITLAB:
                        project = self._get_project(pid)
                        logger.info(f"  [{idx+1}/{len(state['project_ids'])}] {project.path_with_namespace}")
                        branches = self.branch_collector.collect(project)
                        all_branches_dicts.extend([asdict(b) for b in branches])
                    elif self.platform == RepositoryPlatform.GITHUB:
                        repo = self.gh.get_repo(meta["path"])
                        logger.info(f"  [{idx+1}/{len(state['project_ids'])}] {repo.full_name}")
                        # Para GitHub, adaptar colector
                        try:
                            branches = repo.get_branches()
                            for b in branches:
                                all_branches_dicts.append({
                                    "project_id": pid,
                                    "project": repo.full_name,
                                    "branch": b.name,
                                    "default": (b.name == repo.default_branch),
                                    "protected": b.protected,
                                    "last_commit_id": b.commit.sha if b.commit else None,
                                    "last_commit_date": b.commit.commit.committer.date.isoformat() if b.commit and b.commit.commit else None,
                                    "days_since_last_commit": None,  # Se calcularía en post-proceso
                                    "status": "ACTIVA"  # GitHub no proporciona facilmente info de antigüedad
                                })
                        except Exception as e:
                            logger.warning(f"   Error analizando ramas de {repo.full_name}: {e}")
                except Exception as e:
                    logger.warning(f"   Error procesando proyecto {meta.get('path', pid)}: {e}")
                    continue

            state["branches"] = all_branches_dicts
            state["status"] = "branches_analyzed"
            state["messages"].append({"role": "system", "content": f"{len(all_branches_dicts)} ramas analizadas"})
            logger.info(f"✅ {len(all_branches_dicts)} ramas analizadas")
            return state

        def analyze_tags_node(state: GitLabAgentState) -> GitLabAgentState:
            logger.info("🏷️  Analizando tags y releases...")
            all_tags_dicts: List[Dict[str, Any]] = []
            all_releases_dicts: List[Dict[str, Any]] = []

            if self.platform == RepositoryPlatform.GITLAB:
                for pid in state["project_ids"]:
                    project = self._get_project(pid)
                    tags = self.tag_collector.collect_tags(project)
                    releases = self.tag_collector.collect_releases(project)
                    all_tags_dicts.extend([asdict(t) for t in tags])
                    all_releases_dicts.extend([asdict(r) for r in releases])
            elif self.platform == RepositoryPlatform.GITHUB:
                # GitHub: tags/releases tienen estructura diferente
                for meta in state["projects_meta"]:
                    try:
                        repo = self.gh.get_repo(meta["path"])
                        # Tags de GitHub
                        try:
                            for tag in repo.get_tags():
                                all_tags_dicts.append({
                                    "project_id": meta["id"],
                                    "project": meta["path"],
                                    "tag": tag.name,
                                    "is_semver": False,
                                    "commit_id": tag.commit.sha if tag.commit else None,
                                    "date": None,
                                    "days_since": None
                                })
                        except Exception as e:
                            logger.debug(f"   Saltando tags de {meta['path']}: {e}")
                        
                        # Releases de GitHub
                        try:
                            for release in repo.get_releases():
                                all_releases_dicts.append({
                                    "project_id": meta["id"],
                                    "project": meta["path"],
                                    "name": release.title,
                                    "tag_name": release.tag_name,
                                    "created_at": str(release.created_at) if release.created_at else None,
                                    "description_short": release.body[:100] if release.body else ""
                                })
                        except Exception as e:
                            logger.debug(f"   Saltando releases de {meta['path']}: {e}")
                    except Exception as e:
                        logger.warning(f"   Error analizando tags de {meta['path']}: {e}")

            state["tags"] = all_tags_dicts
            state["releases"] = all_releases_dicts
            state["status"] = "tags_analyzed"
            state["messages"].append({
                "role": "system",
                "content": f"{len(all_tags_dicts)} tags y {len(all_releases_dicts)} releases analizados"
            })
            logger.info(f"✅ {len(all_tags_dicts)} tags y {len(all_releases_dicts)} releases")
            return state

        def analyze_artifacts_node(state: GitLabAgentState) -> GitLabAgentState:
            logger.info("📦 Analizando artefactos...")
            all_artifacts_dicts: List[Dict[str, Any]] = []

            if self.platform == RepositoryPlatform.GITLAB:
                for pid in state["project_ids"]:
                    project = self._get_project(pid)
                    artifacts = self.artifact_collector.collect(project)
                    all_artifacts_dicts.extend([asdict(a) for a in artifacts])
            elif self.platform == RepositoryPlatform.GITHUB:
                # GitHub: no tiene "artefactos" en el mismo sentido que GitLab
                # Podría hacer análisis de releases/assets, pero por ahora es N/A
                logger.debug("   GitHub: artefactos no disponibles (no es una característica nativa)")

            state["artifacts"] = all_artifacts_dicts
            state["status"] = "artifacts_analyzed"
            state["messages"].append({"role": "system", "content": f"{len(all_artifacts_dicts)} artefactos analizados"})
            logger.info(f"✅ {len(all_artifacts_dicts)} artefactos analizados")
            return state

        def generate_reports_node(state: GitLabAgentState) -> GitLabAgentState:
            logger.info("📊 Generando reportes...")

            maintenance = self.report_generator.generate(
                state["branches"], state["tags"], state["artifacts"]
            )
            state["maintenance_report"] = maintenance
            self._save_reports(state)

            state["status"] = "reports_generated"
            state["messages"].append({"role": "system", "content": "Reportes generados"})
            logger.info("✅ Reportes generados")
            return state

        def intelligent_analysis_node(state: GitLabAgentState) -> GitLabAgentState:
            if self.analysis_mode == AnalysisMode.INTELLIGENT and self.llm_client:
                logger.info("🧠 Realizando análisis inteligente...")
                insights = self.intelligent_analyzer.analyze(state)
                state["insights"] = insights
                logger.info("✅ Análisis inteligente completado")
            else:
                state["insights"] = "Análisis inteligente no habilitado"

            state["status"] = "completed"
            return state

        # Registro de nodos
        workflow.add_node("init", init_node)
        workflow.add_node("connect_repository", connect_repository_node)
        workflow.add_node("get_projects", get_projects_node)
        workflow.add_node("analyze_branches", analyze_branches_node)
        workflow.add_node("analyze_tags", analyze_tags_node)
        workflow.add_node("analyze_artifacts", analyze_artifacts_node)
        workflow.add_node("generate_reports", generate_reports_node)
        workflow.add_node("intelligent_analysis", intelligent_analysis_node)

        # Flujo
        workflow.add_edge(START, "init")
        workflow.add_edge("init", "connect_repository")

        def should_continue_after_connect(state: GitLabAgentState) -> str:
            return "get_projects" if state["status"] == "connected" else END

        workflow.add_conditional_edges(
            "connect_repository",
            should_continue_after_connect,
            {"get_projects": "get_projects", END: END}
        )

        workflow.add_edge("get_projects", "analyze_branches")
        workflow.add_edge("analyze_branches", "analyze_tags")
        workflow.add_edge("analyze_tags", "analyze_artifacts")
        workflow.add_edge("analyze_artifacts", "generate_reports")
        workflow.add_edge("generate_reports", "intelligent_analysis")
        workflow.add_edge("intelligent_analysis", END)

        return workflow.compile(checkpointer=self.checkpointer)

    def _save_reports(self, state: GitLabAgentState):
        GitLabUtils.save_json(state["branches"],
                              os.path.join(self.output_dir, "inventario_repos_ramas.json"))
        GitLabUtils.save_json({"tags": state["tags"], "releases": state["releases"]},
                              os.path.join(self.output_dir, "catalogo_versiones.json"))
        GitLabUtils.save_json(state["artifacts"],
                              os.path.join(self.output_dir, "catalogo_artefactos.json"))
        if state["maintenance_report"]:
            GitLabUtils.save_json(state["maintenance_report"],
                                  os.path.join(self.output_dir, "reporte_mantenimiento_versiones.json"))
        logger.info(f"📁 Reportes guardados en: {self.output_dir}")

    def run(self) -> Dict[str, Any]:
        logger.info("="*80)
        logger.info(f"🚀 INICIANDO REPOSITORY AGENT - {self.platform.value.upper()}")
        logger.info("="*80)

        try:
            initial_state: GitLabAgentState = {
                "config": {
                    "repository_url": self.repository_url,
                    "project_path": self.project_path,
                    "output_dir": self.output_dir
                },
                "project_ids": [],
                "projects_meta": [],
                "branches": [],
                "tags": [],
                "releases": [],
                "artifacts": [],
                "maintenance_report": None,
                "insights": None,
                "status": "created",
                "error": None,
                "messages": []
            }

            final_state = self.workflow.invoke(
                initial_state,
                config={"configurable": {"thread_id": "gitlab-analysis"}}
            )

            self._print_summary(final_state)

            return {"success": True, "state": final_state, "output_dir": self.output_dir}

        except Exception as e:
            logger.error(f"❌ Error ejecutando agente: {e}")
            return {"success": False, "error": str(e)}

    def _print_summary(self, state: GitLabAgentState):
        print("\n" + "="*80)
        print("📊 RESUMEN DEL ANÁLISIS")
        print("="*80)

        total_projects = len(state.get("project_ids", []))
        print(f"\n📦 PROYECTOS: {total_projects}")

        branches = state.get("branches", [])
        print(f"\n🌿 RAMAS:")
        print(f"   Total: {len(branches)}")
        if branches:
            activas   = [b for b in branches if b.get("status") == BranchStatus.ACTIVE.value]
            latentes  = [b for b in branches if b.get("status") == BranchStatus.LATENT.value]
            inactivas = [b for b in branches if b.get("status") == BranchStatus.INACTIVE.value]
            print(f"   ✅ Activas (≤{self.active_days} días): {len(activas)}")
            print(f"   ⏸️  Latentes ({self.active_days}-{self.stale_days} días): {len(latentes)}")
            print(f"   ❌ Inactivas (>{self.stale_days} días): {len(inactivas)}")

        tags = state.get("tags", [])
        releases = state.get("releases", [])
        print(f"\n🏷️  TAGS Y VERSIONES:")
        print(f"   Total tags: {len(tags)}")
        print(f"   Total releases: {len(releases)}")
        if tags:
            semver = [t for t in tags if t.get("is_semver")]
            print(f"   ✅ Tags semver: {len(semver)}")
            print(f"   ⚠️  Tags no semver: {len(tags) - len(semver)}")

        artifacts = state.get("artifacts", [])
        print(f"\n📦 ARTEFACTOS:")
        if artifacts:
            print(f"   Total: {len(artifacts)}")
            total_size = sum(a.get("artifact_size_bytes") or 0 for a in artifacts)
            print(f"   Tamaño total: {total_size / (1024**2):.2f} MB")
        else:
            print("   ⚠️  No disponible")

        maintenance = state.get("maintenance_report")
        if maintenance:
            print("\n🔧 ALERTAS DE MANTENIMIENTO:")
            print(f"   🗑️  Ramas obsoletas: {len(maintenance.get('ramas_obsoletas', []))}")
            print(f"   🏷️  Tags sin semver: {len(maintenance.get('tags_no_semver', []))}")
            print(f"   ⏳ Tags obsoletos: {len(maintenance.get('tags_obsoletos', []))}")
            print(f"   ⚠️  Artefactos por expirar: {len(maintenance.get('artefactos_por_expirar', []))}")
            print(f"   ❌ Artefactos expirados: {len(maintenance.get('artefactos_expirados', []))}")

        if state.get("insights"):
            print("\n💡 INSIGHTS:")
            print(f"   {state['insights']}")

        print("\n" + "="*80)
        print("✅ Análisis completado")
        print(f"📁 Reportes guardados en: {self.output_dir}")
        print("="*80)

# ========================================================================
# FUNCIÓN MAIN
# ========================================================================

def main():
    """Función principal"""
    ENV_PATH = Path(__file__).resolve().with_name(".env")
    load_dotenv(dotenv_path=ENV_PATH, override=True)

    REPOSITORY_URL = os.getenv("REPOSITORY_URL") or os.getenv("GITLAB_URL", "https://gitlab.com")
    TOKEN = os.getenv("TOKEN") or os.getenv("GITLAB_TOKEN")
    PROJECT_PATH = os.getenv("PROJECT_PATH")
    AUTO_DISCOVER = os.getenv("AUTO_DISCOVER_GROUPS", "true").lower() == "true"

    if not TOKEN:
        print("❌ ERROR: TOKEN no está configurado")
        print("Exporta la variable: export TOKEN='tu-token'")
        sys.exit(1)

    if not REPOSITORY_URL:
        print("❌ ERROR: REPOSITORY_URL o GITLAB_URL no está configurado")
        sys.exit(1)

    # Detectar plataforma
    platform = PlatformDetector.detect_platform(REPOSITORY_URL)
    logger.info(f"🔍 Plataforma detectada: {platform.value}")

    if platform == RepositoryPlatform.GITHUB and not GITHUB_AVAILABLE:
        print("❌ ERROR: PyGithub no está instalado")
        print("Instala con: pip install PyGithub")
        sys.exit(1)

    analysis_mode = AnalysisMode.INTELLIGENT if AZURE_AVAILABLE else AnalysisMode.BASIC

    llm_client = None
    if AZURE_AVAILABLE and analysis_mode == AnalysisMode.INTELLIGENT:
        try:
            provider = get_azure_provider()
            llm_client = provider.get_llm()
            logger.info("✅ LLM habilitado para análisis inteligente")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo inicializar LLM: {e}")
            analysis_mode = AnalysisMode.BASIC

    agent = RepositoryAgent(
        repository_url=REPOSITORY_URL,
        token=TOKEN,
        project_path=PROJECT_PATH,
        auto_discover_groups=AUTO_DISCOVER,
        llm_client=llm_client,
        analysis_mode=analysis_mode
    )

    result = agent.run()
    if result["success"]:
        print("\n🎯 Agente finalizado exitosamente")
        sys.exit(0)
    else:
        print(f"\n❌ Agente finalizado con errores: {result.get('error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
