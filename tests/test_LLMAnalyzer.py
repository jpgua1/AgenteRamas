import unittest
from unittest.mock import patch, MagicMock
import os
import sys
sys.modules['langchain_openai'] = MagicMock()
sys.modules['langchain.prompts'] = MagicMock()
sys.modules['langchain.output_parsers'] = MagicMock()
sys.modules['langchain_core.prompts'] = MagicMock()
sys.modules['langchain_core.output_parsers'] = MagicMock()
import LLMAnalyzer

class TestLLMAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = LLMAnalyzer.LLMAnalyzer()

    def test_fallback_summary_critical(self):
        data = {"analysis": {"total_inactive_branches": 6, "total_branches": 10, "total_obsolete_tags": 2, "artifacts_expiring_soon": 1}}
        summary = self.analyzer._fallback_summary(data)
        self.assertIn("executive_summary", summary)
        self.assertIn("risk_level", summary)
        self.assertTrue(summary["health_score"] <= 80)

    def test_fallback_branch_analysis_inactive(self):
        branch = {"days_since_last_commit": 200, "status": "INACTIVA", "last_commit_date": "2024-01-01"}
        result = self.analyzer._fallback_branch_analysis(branch)
        self.assertEqual(result["recommended_action"], "ELIMINAR")
        self.assertEqual(result["risk_level"], "\U0001F534 CRÍTICO")

    def test_fallback_branch_analysis_active(self):
        branch = {"days_since_last_commit": 2, "status": "ACTIVA", "last_commit_date": "2024-06-01"}
        result = self.analyzer._fallback_branch_analysis(branch)
        self.assertEqual(result["recommended_action"], "MANTENER")
        self.assertEqual(result["risk_level"], "\U0001F7E2 SEGURA")

    def test_fallback_cleanup_plan(self):
        data = {"projects": []}
        plan = self.analyzer._fallback_cleanup_plan(data)
        self.assertIn("phase_1_delete_now", plan)
        self.assertIn("phase_2_review", plan)
        self.assertIn("phase_3_archive", plan)

    def test_generate_executive_summary_no_llm(self):
        data = {"analysis": {"total_inactive_branches": 2, "total_branches": 10, "total_obsolete_tags": 1, "artifacts_expiring_soon": 0}, "projects": []}
        self.analyzer.llm = None
        summary = self.analyzer.generate_executive_summary(data)
        self.assertIn("executive_summary", summary)

    def test_analyze_branch_health_no_llm(self):
        branch = {"days_since_last_commit": 100, "status": "INACTIVA", "last_commit_date": "2024-01-01"}
        self.analyzer.llm = None
        result = self.analyzer.analyze_branch_health(branch, "repo")
        self.assertIn("risk_level", result)

    def test_generate_cleanup_recommendations_no_llm(self):
        data = {"projects": []}
        self.analyzer.llm = None
        plan = self.analyzer.generate_cleanup_recommendations(data)
        self.assertIn("phase_1_delete_now", plan)

if __name__ == "__main__":
    unittest.main()
