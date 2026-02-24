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
        data = {"analysis": {"total_inactive_branches": 60, "total_branches": 100, "total_obsolete_tags": 5, "artifacts_expiring_soon": 2}}
        summary = self.analyzer._fallback_summary(data)
        self.assertEqual(summary["risk_level"], "\U0001F534 CRÍTICO")
        self.assertIn("ramas inactivas", summary["top_risks"][0])

    def test_fallback_summary_bajo(self):
        data = {"analysis": {"total_inactive_branches": 2, "total_branches": 100, "total_obsolete_tags": 1, "artifacts_expiring_soon": 0}}
        summary = self.analyzer._fallback_summary(data)
        self.assertEqual(summary["risk_level"], "\U0001F7E2 BAJO")

    def test_fallback_branch_analysis_critical(self):
        branch = {"status": "INACTIVA", "days_since_last_commit": 200, "last_commit_date": "2023-01-01"}
        analysis = self.analyzer._fallback_branch_analysis(branch)
        self.assertEqual(analysis["risk_level"], "\U0001F534 CRÍTICO")
        self.assertEqual(analysis["recommended_action"], "ELIMINAR")

    def test_fallback_branch_analysis_segura(self):
        branch = {"status": "ACTIVA", "days_since_last_commit": 2, "last_commit_date": "2024-01-01"}
        analysis = self.analyzer._fallback_branch_analysis(branch)
        self.assertEqual(analysis["risk_level"], "\U0001F7E2 SEGURA")
        self.assertEqual(analysis["recommended_action"], "MANTENER")

    def test_fallback_cleanup_plan(self):
        plan = self.analyzer._fallback_cleanup_plan({})
        self.assertIn("phase_1_delete_now", plan)
        self.assertIn("phase_2_review", plan)
        self.assertIn("phase_3_archive", plan)

    def test_generate_executive_summary_no_llm(self):
        data = {"analysis": {"total_inactive_branches": 10, "total_branches": 100, "total_obsolete_tags": 2, "artifacts_expiring_soon": 1}, "projects": []}
        summary = self.analyzer.generate_executive_summary(data)
        self.assertIn("executive_summary", summary)

    def test_analyze_branch_health_no_llm(self):
        branch = {"status": "INACTIVA", "days_since_last_commit": 100, "last_commit_date": "2023-01-01"}
        analysis = self.analyzer.analyze_branch_health(branch, "TestProject")
        self.assertIn("risk_level", analysis)

    def test_generate_cleanup_recommendations_no_llm(self):
        data = {"projects": [{"name": "Test", "branches": [{"status": "INACTIVA", "days_since_last_commit": 100, "name": "b1", "last_commit_date": "2023-01-01"}]}]}
        plan = self.analyzer.generate_cleanup_recommendations(data)
        self.assertIn("phase_1_delete_now", plan)

if __name__ == "__main__":
    unittest.main()
