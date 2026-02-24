import unittest
from unittest.mock import patch, MagicMock
import LLMAnalyzer

class TestLLMAnalyzer(unittest.TestCase):
    @patch("LLMAnalyzer.AzureChatOpenAI", autospec=True)
    @patch("LLMAnalyzer.os.getenv")
    def test_init_llm_none_when_no_env(self, mock_getenv, mock_azure):
        mock_getenv.return_value = None
        analyzer = LLMAnalyzer.LLMAnalyzer()
        self.assertIsNone(analyzer.llm)

    @patch("LLMAnalyzer.AzureChatOpenAI", autospec=True)
    @patch("LLMAnalyzer.os.getenv")
    def test_init_llm_success(self, mock_getenv, mock_azure):
        mock_getenv.side_effect = lambda k, d=None: "dummy" if k in ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"] else d
        analyzer = LLMAnalyzer.LLMAnalyzer()
        self.assertIsNotNone(analyzer.llm)

    def test_fallback_summary_levels(self):
        analyzer = LLMAnalyzer.LLMAnalyzer()
        analyzer.llm = None
        # CRÍTICO
        data = {"analysis": {"total_inactive_branches": 60, "total_branches": 100}}
        res = analyzer._fallback_summary(data)
        self.assertIn("CR\u00cdTICO", res["risk_level"])
        # ALTO
        data = {"analysis": {"total_inactive_branches": 40, "total_branches": 100}}
        res = analyzer._fallback_summary(data)
        self.assertIn("ALTO", res["risk_level"])
        # MEDIO
        data = {"analysis": {"total_inactive_branches": 20, "total_branches": 100}}
        res = analyzer._fallback_summary(data)
        self.assertIn("MEDIO", res["risk_level"])
        # BAJO
        data = {"analysis": {"total_inactive_branches": 5, "total_branches": 100}}
        res = analyzer._fallback_summary(data)
        self.assertIn("BAJO", res["risk_level"])

    def test_fallback_branch_analysis(self):
        analyzer = LLMAnalyzer.LLMAnalyzer()
        analyzer.llm = None
        # CRÍTICO
        branch = {"status": "INACTIVA", "days_since_last_commit": 200, "last_commit_date": "2023-01-01"}
        res = analyzer._fallback_branch_analysis(branch)
        self.assertIn("CR\u00cdTICO", res["risk_level"])
        self.assertEqual(res["recommended_action"], "ELIMINAR")
        # ALTO
        branch = {"status": "INACTIVA", "days_since_last_commit": 100, "last_commit_date": "2023-01-01"}
        res = analyzer._fallback_branch_analysis(branch)
        self.assertIn("ALTO", res["risk_level"])
        self.assertEqual(res["recommended_action"], "REVISAR")
        # MEDIO
        branch = {"status": "INACTIVA", "days_since_last_commit": 50, "last_commit_date": "2023-01-01"}
        res = analyzer._fallback_branch_analysis(branch)
        self.assertIn("MEDIO", res["risk_level"])
        self.assertEqual(res["recommended_action"], "ARCHIVAR")
        # SEGURA
        branch = {"status": "ACTIVA", "days_since_last_commit": 1, "last_commit_date": "2023-01-01"}
        res = analyzer._fallback_branch_analysis(branch)
        self.assertIn("SEGURA", res["risk_level"])
        self.assertEqual(res["recommended_action"], "MANTENER")

    def test_fallback_cleanup_plan(self):
        analyzer = LLMAnalyzer.LLMAnalyzer()
        analyzer.llm = None
        plan = analyzer._fallback_cleanup_plan({})
        self.assertIn("phase_1_delete_now", plan)
        self.assertIn("phase_2_review", plan)
        self.assertIn("phase_3_archive", plan)

    def test_get_llm_analyzer_factory(self):
        analyzer = LLMAnalyzer.get_llm_analyzer()
        self.assertIsInstance(analyzer, LLMAnalyzer.LLMAnalyzer)

if __name__ == "__main__":
    unittest.main()
