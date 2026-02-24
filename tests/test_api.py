import unittest
from fastapi.testclient import TestClient
import api

class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_root(self):
        response = self.client.get("/api/v1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.json())

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

    def test_analyze_missing_token(self):
        req = {
            "repository_url": "https://gitlab.com/group/project",
            "token": None,
            "auto_discover_groups": True
        }
        response = self.client.post("/api/v1/analyze", json=req)
        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.json())

    def test_analyze_unknown_platform(self):
        req = {
            "repository_url": "https://unknownhost.com/repo",
            "token": "dummy",
            "auto_discover_groups": True
        }
        response = self.client.post("/api/v1/analyze", json=req)
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_analyze_missing_project_path(self):
        req = {
            "repository_url": "https://gitlab.com/group/project",
            "token": "dummy",
            "auto_discover_groups": False,
            "project_path": None
        }
        response = self.client.post("/api/v1/analyze", json=req)
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

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
