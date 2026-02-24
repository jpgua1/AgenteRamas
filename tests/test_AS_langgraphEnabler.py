import unittest
from unittest.mock import patch, MagicMock
import AS_langgraphEnabler as ag
from datetime import datetime, timezone

class TestPlatformDetector(unittest.TestCase):
    def test_detect_platform_github(self):
        url = "https://github.com/org/repo"
        self.assertEqual(ag.PlatformDetector.detect_platform(url), ag.RepositoryPlatform.GITHUB)

    def test_detect_platform_gitlab(self):
        url = "https://gitlab.com/group/repo"
        self.assertEqual(ag.PlatformDetector.detect_platform(url), ag.RepositoryPlatform.GITLAB)

    def test_detect_platform_azure(self):
        url = "https://dev.azure.com/org/project"
        self.assertEqual(ag.PlatformDetector.detect_platform(url), ag.RepositoryPlatform.AZURE_DEVOPS)

    def test_detect_platform_unknown_defaults_gitlab(self):
        url = "https://customgitserver.com/repo"
        self.assertEqual(ag.PlatformDetector.detect_platform(url), ag.RepositoryPlatform.GITLAB)

    def test_get_api_url_github(self):
        url = "https://github.com/org/repo"
        self.assertEqual(ag.PlatformDetector.get_api_url(url), "https://api.github.com")

    def test_get_api_url_gitlab(self):
        url = "https://gitlab.com/group/repo"
        self.assertEqual(ag.PlatformDetector.get_api_url(url), "https://gitlab.com")

    def test_get_api_url_azure(self):
        url = "https://dev.azure.com/org/project"
        self.assertEqual(ag.PlatformDetector.get_api_url(url), "https://dev.azure.com")

class TestGitLabUtils(unittest.TestCase):
    def test_is_semver(self):
        self.assertTrue(ag.GitLabUtils.is_semver("v1.2.3"))
        self.assertTrue(ag.GitLabUtils.is_semver("1.2.3"))
        self.assertFalse(ag.GitLabUtils.is_semver("feature-branch"))

    def test_utcnow(self):
        now = ag.GitLabUtils.utcnow()
        self.assertIsInstance(now, datetime)
        self.assertEqual(now.tzinfo, timezone.utc)

    def test_parse_iso_valid(self):
        dt_str = "2024-06-01T12:00:00Z"
        dt = ag.GitLabUtils.parse_iso(dt_str)
        self.assertIsInstance(dt, datetime)

    def test_days_ago(self):
        dt = datetime.now(timezone.utc)
        self.assertEqual(ag.GitLabUtils.days_ago(dt), 0)

class TestBranchCollector(unittest.TestCase):
    @patch("AS_langgraphEnabler.GitLabUtils.gl_list_all")
    def test_collect_success(self, mock_gl_list_all):
        branch_mock = MagicMock()
        branch_mock.name = "main"
        branch_mock.commit = {"committed_date": "2024-06-01T12:00:00Z", "id": "abc123"}
        branch_mock.default = True
        branch_mock.protected = False
        project_mock = MagicMock()
        project_mock.id = 1
        project_mock.path_with_namespace = "org/repo"
        mock_gl_list_all.return_value = [branch_mock]
        collector = ag.BranchCollector()
        result = collector.collect(project_mock)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].branch, "main")

    @patch("AS_langgraphEnabler.GitLabUtils.gl_list_all", side_effect=Exception("fail"))
    def test_collect_error(self, mock_gl_list_all):
        project_mock = MagicMock()
        project_mock.id = 1
        project_mock.path_with_namespace = "org/repo"
        collector = ag.BranchCollector()
        result = collector.collect(project_mock)
        self.assertEqual(result, [])

class TestTagCollector(unittest.TestCase):
    @patch("AS_langgraphEnabler.GitLabUtils.gl_list_all")
    def test_collect_tags(self, mock_gl_list_all):
        tag_mock = MagicMock()
        tag_mock.name = "v1.0.0"
        tag_mock.commit = {"committed_date": "2024-06-01T12:00:00Z", "id": "abc123"}
        project_mock = MagicMock()
        project_mock.id = 1
        project_mock.path_with_namespace = "org/repo"
        mock_gl_list_all.return_value = [tag_mock]
        collector = ag.TagCollector()
        result = collector.collect_tags(project_mock)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].tag, "v1.0.0")

    @patch("AS_langgraphEnabler.GitLabUtils.gl_list_all", side_effect=Exception("fail"))
    def test_collect_tags_error(self, mock_gl_list_all):
        project_mock = MagicMock()
        project_mock.id = 1
        project_mock.path_with_namespace = "org/repo"
        collector = ag.TagCollector()
        result = collector.collect_tags(project_mock)
        self.assertEqual(result, [])

class TestReportGenerator(unittest.TestCase):
    def test_generate(self):
        branches = [{"status": "INACTIVA"}, {"status": "ACTIVA"}]
        tags = [{"is_semver": False, "days_since": 100}, {"is_semver": True, "days_since": 10}]
        artifacts = [{"artifact_days_to_expire": 3}, {"artifact_days_to_expire": -1}]
        gen = ag.ReportGenerator()
        report = gen.generate(branches, tags, artifacts)
        self.assertIn("ramas_obsoletas", report)
        self.assertIn("tags_no_semver", report)
        self.assertIn("artefactos_por_expirar", report)

if __name__ == "__main__":
    unittest.main()
