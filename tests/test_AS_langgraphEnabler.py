import unittest
from unittest.mock import patch, MagicMock
import AS_langgraphEnabler as ag

class TestPlatformDetector(unittest.TestCase):
    def test_detect_platform_gitlab(self):
        self.assertEqual(ag.PlatformDetector.detect_platform("https://gitlab.com/group/project"), ag.RepositoryPlatform.GITLAB)
        self.assertEqual(ag.PlatformDetector.detect_platform("https://gitlab.example.com"), ag.RepositoryPlatform.GITLAB)
    def test_detect_platform_github(self):
        self.assertEqual(ag.PlatformDetector.detect_platform("https://github.com/user/repo"), ag.RepositoryPlatform.GITHUB)
    def test_detect_platform_azure(self):
        self.assertEqual(ag.PlatformDetector.detect_platform("https://dev.azure.com/org/project"), ag.RepositoryPlatform.AZURE_DEVOPS)
        self.assertEqual(ag.PlatformDetector.detect_platform("https://org.visualstudio.com/project"), ag.RepositoryPlatform.AZURE_DEVOPS)
    def test_detect_platform_unknown_defaults_gitlab(self):
        self.assertEqual(ag.PlatformDetector.detect_platform("https://unknown.com/repo"), ag.RepositoryPlatform.GITLAB)
    def test_get_api_url(self):
        self.assertEqual(ag.PlatformDetector.get_api_url("https://github.com/user/repo"), "https://api.github.com")
        self.assertEqual(ag.PlatformDetector.get_api_url("https://dev.azure.com/org/project"), "https://dev.azure.com")
        self.assertEqual(ag.PlatformDetector.get_api_url("https://gitlab.com/group/project"), "https://gitlab.com")

class TestGitLabUtils(unittest.TestCase):
    def test_is_semver(self):
        self.assertTrue(ag.GitLabUtils.is_semver("1.2.3"))
        self.assertTrue(ag.GitLabUtils.is_semver("v1.2.3"))
        self.assertFalse(ag.GitLabUtils.is_semver("1.2"))
        self.assertFalse(ag.GitLabUtils.is_semver("main"))
    def test_days_ago(self):
        from datetime import timedelta
        now = ag.GitLabUtils.utcnow()
        dt = now - timedelta(days=5)
        self.assertEqual(ag.GitLabUtils.days_ago(dt), 5)
    def test_parse_iso(self):
        dt = ag.GitLabUtils.parse_iso("2024-01-01T12:00:00Z")
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 1)

class TestReportGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = ag.ReportGenerator(stale_days=90, artifact_days_soon=7)
    def test_generate(self):
        branches = [
            {"status": ag.BranchStatus.INACTIVE.value},
            {"status": ag.BranchStatus.ACTIVE.value},
        ]
        tags = [
            {"is_semver": False, "days_since": 100},
            {"is_semver": True, "days_since": 10},
        ]
        artifacts = [
            {"artifact_days_to_expire": 3},
            {"artifact_days_to_expire": -1},
        ]
        report = self.generator.generate(branches, tags, artifacts)
        self.assertEqual(len(report["ramas_obsoletas"]), 1)
        self.assertEqual(len(report["tags_no_semver"]), 1)
        self.assertEqual(len(report["tags_obsoletos"]), 1)
        self.assertEqual(len(report["artefactos_por_expirar"]), 1)
        self.assertEqual(len(report["artefactos_expirados"]), 1)

class TestIntelligentAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = ag.IntelligentAnalyzer()
    def test_analyze_no_llm(self):
        state = {"branches": [], "maintenance_report": None}
        result = self.analyzer.analyze(state)
        self.assertIn("No se detectaron problemas", result)

if __name__ == "__main__":
    unittest.main()
