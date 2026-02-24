import unittest
from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/../'))
import api

class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_root(self):
        response = self.client.get("/api/v1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("GitLab Agent API", response.json().get("message", ""))

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    @patch("api.create_job", return_value="jobid123")
    @patch("api.update_job")
    @patch("api.RepositoryAgent")
    def test_analyze_post_missing_token(self, mock_agent, mock_update_job, mock_create_job):
        req = {
            "repository_url": "https://gitlab.com/org/repo",
            "token": "",
            "auto_discover_groups": True
        }
        # Remove token from env
        if "TOKEN" in os.environ:
            del os.environ["TOKEN"]
        response = self.client.post("/api/v1/analyze", json=req)
        self.assertEqual(response.status_code, 401)

    def test_list_outputs(self):
        response = self.client.get("/api/v1/outputs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("outputs", response.json())

    def test_list_jobs(self):
        response = self.client.get("/api/v1/jobs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("jobs", response.json())

if __name__ == "__main__":
    unittest.main()
