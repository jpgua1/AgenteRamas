import unittest
from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import patch, MagicMock

sys.modules['AS_langgraphEnabler'] = MagicMock()
sys.modules['AS_langgraphEnabler'].AnalysisMode.BASIC = 'basic'
sys.modules['AS_langgraphEnabler'].PlatformDetector.detect_platform.return_value = MagicMock(value='gitlab')
sys.modules['AS_langgraphEnabler'].RepositoryAgent = MagicMock()
sys.modules['LLMAnalyzer'] = MagicMock()
sys.modules['LLMAnalyzer'].get_llm_analyzer.return_value = MagicMock()

import api

class TestApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_root(self):
        resp = self.client.get("/api/v1")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("message", resp.json())

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("status", resp.json())

    @patch.dict(os.environ, {"TOKEN": "dummy", "REPOSITORY_URL": "https://gitlab.com"})
    def test_analyze_missing_project_path(self):
        req = {
            "auto_discover_groups": False,
            "project_path": None,
            "active_days": 30,
            "stale_days": 90,
            "artifact_days_soon": 7,
            "max_pipelines": 50,
            "analysis_mode": "basic"
        }
        resp = self.client.post("/api/v1/analyze", json=req)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Debe especificar", resp.text)

    @patch.dict(os.environ, {"TOKEN": "dummy", "REPOSITORY_URL": "https://gitlab.com"})
    def test_analyze_success(self):
        req = {
            "auto_discover_groups": True,
            "active_days": 30,
            "stale_days": 90,
            "artifact_days_soon": 7,
            "max_pipelines": 50,
            "analysis_mode": "basic"
        }
        resp = self.client.post("/api/v1/analyze", json=req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("job_id", resp.json())
        self.assertIn("status", resp.json())

    def test_list_outputs(self):
        resp = self.client.get("/api/v1/outputs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("outputs", resp.json())

    def test_list_jobs(self):
        resp = self.client.get("/api/v1/jobs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("jobs", resp.json())

if __name__ == "__main__":
    unittest.main()
