"""
LLM Analyzer - Genera insights y recomendaciones inteligentes usando LLM
Convierte datos brutos en decisiones accionables con explicaciones detalladas
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Azure OpenAI via LangChain
from langchain_openai import AzureChatOpenAI
try:
    from langchain.prompts import ChatPromptTemplate
except ImportError:
    from langchain_core.prompts import ChatPromptTemplate
try:
    from langchain.output_parsers import JsonOutputParser
except ImportError:
    from langchain_core.output_parsers import JsonOutputParser

logger = logging.getLogger(__name__)
load_dotenv()

class LLMAnalyzer:
    """Analizador que usa LLM para generar insights y recomendaciones"""
    
    def __init__(self):
        """Inicializar el cliente LLM"""
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
        
        if not api_key or not endpoint:
            logger.warning("⚠️ Credenciales de Azure OpenAI no configuradas. LLM deshabilitado.")
            self.llm = None
            return
        
        try:
            self.llm = AzureChatOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=endpoint,
                deployment_name=deployment,
                temperature=0.3,  # Determinístico para análisis
                max_tokens=2000,
            )
            logger.info(f"✅ LLM inicializado: {deployment}")
        except Exception as e:
            logger.warning(f"⚠️ Error inicializando LLM: {e}")
            self.llm = None
    
    def generate_executive_summary(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Genera un resumen ejecutivo por grupo/proyecto
        Incluye: estado general, top riesgos, acciones inmediatas
        """
        if not self.llm:
            return self._fallback_summary(analysis_data)
        
        try:
            analysis = analysis_data.get("analysis", {})
            projects = analysis_data.get("projects", [])
            
            # Preparar datos para el LLM
            inactive_branches = analysis.get("total_inactive_branches", 0)
            total_branches = analysis.get("total_branches", 1)
            obsolete_tags = analysis.get("total_obsolete_tags", 0)
            expiring_artifacts = analysis.get("artifacts_expiring_soon", 0)
            expired_artifacts = analysis.get("artifacts_expired", 0)
            
            inactivity_rate = (inactive_branches / total_branches * 100) if total_branches > 0 else 0
            
            prompt = ChatPromptTemplate.from_template("""
Eres un experto en gestión de repositorios Git. Analiza los siguientes datos y genera un resumen ejecutivo:

📊 DATOS:
- Total de proyectos: {num_projects}
- Total de ramas: {total_branches}
- Ramas inactivas: {inactive_branches} ({inactivity_rate:.1f}%)
- Releases/Tags obsoletos: {obsolete_tags}
- Artefactos por expirar: {expiring_artifacts}
- Artefactos expirados: {expired_artifacts}

Proyectos con más ramas inactivas:
{top_projects}

Genera un JSON con:
{{
  "executive_summary": "2 párrafos describiendo el estado general",
  "risk_level": "🔴 CRÍTICO|🟠 ALTO|🟡 MEDIO|🟢 BAJO",
  "top_risks": ["riesgo 1 con explicación", "riesgo 2...", ...],
  "immediate_actions": ["acción 1 con prioridad", "acción 2...", ...],
  "health_score": 0-100,
  "recommendations": ["recomendación 1", "recomendación 2", ...]
}}
""")
            
            # Top 3 proyectos con más ramas inactivas
            top_projects_list = sorted(
                [(p["name"], len([b for b in p.get("branches", []) if b.get("status") == "INACTIVA"])) 
                 for p in projects],
                key=lambda x: x[1],
                reverse=True
            )[:3]
            
            top_projects_str = "\n".join([f"  - {name}: {count} inactivas" for name, count in top_projects_list])
            
            chain = prompt | self.llm
            result = chain.invoke({
                "num_projects": len(projects),
                "total_branches": total_branches,
                "inactive_branches": inactive_branches,
                "inactivity_rate": inactivity_rate,
                "obsolete_tags": obsolete_tags,
                "expiring_artifacts": expiring_artifacts,
                "expired_artifacts": expired_artifacts,
                "top_projects": top_projects_str,
            })
            
            # Parsear JSON
            content = result.content
            try:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    summary = json.loads(json_str)
                    logger.info("✅ Executive summary generado por LLM")
                    return summary
            except json.JSONDecodeError:
                logger.warning("⚠️ Error parseando JSON del LLM")
                return self._fallback_summary(analysis_data)
        
        except Exception as e:
            logger.error(f"❌ Error generando executive summary: {e}")
            return self._fallback_summary(analysis_data)
    
    def analyze_branch_health(self, branch: Dict[str, Any], project_name: str) -> Dict[str, Any]:
        """
        Analiza la salud de una rama individual
        Retorna: riesgo, justificación, acciones recomendadas
        """
        if not self.llm:
            return self._fallback_branch_analysis(branch)
        
        try:
            status = branch.get("status", "DESCONOCIDO")
            days_since_commit = branch.get("days_since_last_commit", -1)
            last_commit = branch.get("last_commit_date", "desconocido")
            
            prompt = ChatPromptTemplate.from_template("""
Eres un experto en limpieza de repositorios. Analiza esta rama Git:

🌿 RAMA: {branch_name}
📁 PROYECTO: {project_name}
📊 ESTADO: {status}
📅 ÚLTIMO COMMIT: {last_commit}
⏰ DÍAS SIN ACTIVIDAD: {days_since_commit}

Genera un JSON con:
{{
  "risk_score": 0-100,
  "risk_level": "🔴 CRÍTICO|🟠 ALTO|🟡 MEDIO|🟢 BAJO|🟢 SEGURA",
  "reason": "Explicación clara de por qué esta rama es riesgosa o segura",
  "evidence": ["evidencia 1", "evidencia 2", ...],
  "recommended_action": "ELIMINAR|REVISAR|MANTENER|ARCHIVAR",
  "priority": 1-5,
  "estimated_impact": "Impacto de la acción recomendada"
}}
""")
            
            chain = prompt | self.llm
            result = chain.invoke({
                "branch_name": branch.get("name", "unknown"),
                "project_name": project_name,
                "status": status,
                "last_commit": last_commit,
                "days_since_commit": days_since_commit,
            })
            
            content = result.content
            try:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    analysis = json.loads(json_str)
                    return analysis
            except json.JSONDecodeError:
                return self._fallback_branch_analysis(branch)
        
        except Exception as e:
            logger.error(f"❌ Error analizando rama {branch.get('name')}: {e}")
            return self._fallback_branch_analysis(branch)
    
    def generate_cleanup_recommendations(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Genera un plan de limpieza priorizado
        Incluye: qué eliminar ya, qué esperar, por qué, riesgos
        """
        if not self.llm:
            return self._fallback_cleanup_plan(analysis_data)
        
        try:
            projects = analysis_data.get("projects", [])
            
            # Recopilar ramas inactivas
            inactive_branches = []
            for project in projects:
                for branch in project.get("branches", []):
                    if branch.get("status") == "INACTIVA":
                        inactive_branches.append({
                            "name": branch.get("name"),
                            "project": project.get("name"),
                            "days": branch.get("days_since_last_commit", -1),
                            "last_commit": branch.get("last_commit_date"),
                        })
            
            # Top 10 más inactivas
            top_inactive = sorted(
                inactive_branches,
                key=lambda x: x.get("days", 0),
                reverse=True
            )[:10]
            
            branches_summary = json.dumps(top_inactive, ensure_ascii=False, indent=2)
            
            prompt = ChatPromptTemplate.from_template("""
Eres un experto en DevOps limpieza de repositorios. Genera un plan de limpieza priorizado:

📋 RAMAS INACTIVAS A CONSIDERAR:
{branches_summary}

Genera un JSON con un plan de 3 fases:
{{
  "phase_1_delete_now": {{
    "priority": "🔴 CRÍTICA",
    "branches": ["rama1 - justificación", ...],
    "rationale": "Por qué hacer esto ahora",
    "risks": ["riesgo 1", ...],
    "estimated_time": "X minutos"
  }},
  "phase_2_review": {{
    "priority": "🟠 ALTA",
    "branches": ["rama1 - justificación", ...],
    "rationale": "Por qué revisar primero",
    "steps": ["paso 1", "paso 2", ...]
  }},
  "phase_3_archive": {{
    "priority": "🟡 MEDIA",
    "branches": ["rama1 - justificación", ...],
    "rationale": "Por qué archivar en lugar de eliminar",
    "automation": "Script recomendado"
  }}
}}
""")
            
            chain = prompt | self.llm
            result = chain.invoke({
                "branches_summary": branches_summary,
            })
            
            content = result.content
            try:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    plan = json.loads(json_str)
                    logger.info("✅ Cleanup plan generado por LLM")
                    return plan
            except json.JSONDecodeError:
                return self._fallback_cleanup_plan(analysis_data)
        
        except Exception as e:
            logger.error(f"❌ Error generando cleanup plan: {e}")
            return self._fallback_cleanup_plan(analysis_data)
    
    # ============ FALLBACK (sin LLM) ============
    
    def _fallback_summary(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Resumen fallback sin LLM"""
        analysis = analysis_data.get("analysis", {})
        inactive = analysis.get("total_inactive_branches", 0)
        total = analysis.get("total_branches", 1)
        rate = (inactive / total * 100) if total > 0 else 0
        
        if rate > 50:
            risk_level = "🔴 CRÍTICO"
            health_score = 20
        elif rate > 30:
            risk_level = "🟠 ALTO"
            health_score = 40
        elif rate > 10:
            risk_level = "🟡 MEDIO"
            health_score = 60
        else:
            risk_level = "🟢 BAJO"
            health_score = 80
        
        return {
            "executive_summary": f"El repositorio tiene {rate:.1f}% de ramas inactivas ({inactive}/{total}). Esto indica {['buena salud', 'salud regular', 'baja salud'][min(2, int(rate/33))]}.",
            "risk_level": risk_level,
            "top_risks": [
                f"🌿 {inactive} ramas inactivas acumulan deuda técnica",
                f"📦 {analysis.get('total_obsolete_tags', 0)} tags obsoletos sin limpieza",
                f"⏰ {analysis.get('artifacts_expiring_soon', 0)} artefactos por expirar",
            ],
            "immediate_actions": [
                "1️⃣ Revisar ramas inactivas > 90 días",
                "2️⃣ Limpiar tags obsoletos",
                "3️⃣ Planificar expiración de artefactos",
            ],
            "health_score": health_score,
            "recommendations": [
                "Establecer política de limpieza de ramas",
                "Automatizar notificaciones de ramas inactivas",
                "Documentar criterios de retención",
            ]
        }
    
    def _fallback_branch_analysis(self, branch: Dict[str, Any]) -> Dict[str, Any]:
        """Análisis fallback de rama sin LLM"""
        days = branch.get("days_since_last_commit", -1)
        status = branch.get("status", "DESCONOCIDO")
        
        if status == "INACTIVA" and days > 180:
            risk_level = "🔴 CRÍTICO"
            risk_score = 90
            action = "ELIMINAR"
        elif status == "INACTIVA" and days > 90:
            risk_level = "🟠 ALTO"
            risk_score = 70
            action = "REVISAR"
        elif status == "INACTIVA":
            risk_level = "🟡 MEDIO"
            risk_score = 40
            action = "ARCHIVAR"
        else:
            risk_level = "🟢 SEGURA"
            risk_score = 10
            action = "MANTENER"
        
        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "reason": f"Rama {status.lower()} con {days} días sin actividad",
            "evidence": [f"Último commit: {branch.get('last_commit_date')}"],
            "recommended_action": action,
            "priority": 5 - min(4, int(risk_score / 25)),
            "estimated_impact": f"Reduce deuda técnica en {min(100, days//30)}%"
        }
    
    def _fallback_cleanup_plan(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Plan fallback sin LLM"""
        return {
            "phase_1_delete_now": {
                "priority": "🔴 CRÍTICA",
                "branches": ["Ramas inactivas > 180 días"],
                "rationale": "Eliminar deuda técnica inmediata",
                "risks": ["Revisar MRs pendientes primero"],
                "estimated_time": "30 minutos"
            },
            "phase_2_review": {
                "priority": "🟠 ALTA",
                "branches": ["Ramas inactivas 90-180 días"],
                "rationale": "Validar que no hay trabajo en progreso",
                "steps": ["Listar PRs/MRs", "Contactar dueños", "Marcar para eliminación"]
            },
            "phase_3_archive": {
                "priority": "🟡 MEDIA",
                "branches": ["Ramas inactivas 30-90 días"],
                "rationale": "Archivar en repositorio histórico",
                "automation": "Usar script git-archive"
            }
        }


def get_llm_analyzer() -> LLMAnalyzer:
    """Factory para obtener instancia del analizador"""
    return LLMAnalyzer()
