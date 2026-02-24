import unittest
from unittest.mock import MagicMock, patch
import AS_langgraphEnabler as ag
from datetime import datetime, timezone

class TestPlatformDetector(unittest.TestCase):
    def test_detect_platform_github(self):
        url = "https://github.com/user/repo"
        self.assertEqual(ag.PlatformDetector.detect_platform(url), ag.RepositoryPlatform.GITHUB)
    def test_detect_platform_gitlab(self):
        url = "https://gitlab.com/group/project"
        self.assertEqual(ag.PlatformDetector.detect_platform(url), ag.RepositoryPlatform.GITLAB)
    def test_detect_platform_azure(self):
        url = "https://dev.azure.com/org/project"
        self.assertEqual(ag.PlatformDetector.detect_platform(url), ag.RepositoryPlatform.AZURE_DEVOPS)
    def test_detect_platform_unknown_defaults_gitlab(self):
        url = "https://customdomain.com/repo"
        self.assertEqual(ag.PlatformDetector.detect_platform(url), ag.RepositoryPlatform.GITLAB)
    def test_get_api_url_github(self):
        url = "https://github.com/user/repo"
        self.assertEqual(ag.PlatformDetector.get_api_url(url), "https://api.github.com")
    def test_get_api_url_gitlab(self):
        url = "https://gitlab.com/group/project"
        self.assertEqual(ag.PlatformDetector.get_api_url(url), "https://gitlab.com")
    def test_get_api_url_azure(self):
        url = "https://dev.azure.com/org/project"
        self.assertEqual(ag.PlatformDetector.get_api_url(url), "https://dev.azure.com")

class TestGitLabUtils(unittest.TestCase):
    def test_utcnow(self):
        now = ag.GitLabUtils.utcnow()
        self.assertIsInstance(now, datetime)
        self.assertEqual(now.tzinfo, timezone.utc)
    def test_parse_iso_valid(self):
        dt_str = "2024-01-01T12:00:00.000Z"
        dt = ag.GitLabUtils.parse_iso(dt_str)
        self.assertIsInstance(dt, datetime)
    def test_days_ago(self):
        dt = datetime.now(timezone.utc)
        self.assertEqual(ag.GitLabUtils.days_ago(dt), 0)
    def test_is_semver(self):
        self.assertTrue(ag.GitLabUtils.is_semver("v1.2.3"))
        self.assertFalse(ag.GitLabUtils.is_semver("feature-branch"))

class TestBranchCollector(unittest.TestCase):
    @patch("AS_langgraphEnabler.gitlab")
    def test_collect_handles_gitlab_list_error(self, mock_gitlab):
        project = MagicMock()
        project.branches.list.side_effect = mock_gitlab.exceptions.GitlabListError("fail")
        collector = ag.BranchCollector()
        branches = collector.collect(project)
        self.assertEqual(branches, [])
    def test_collect_handles_exception(self):
        project = MagicMock()
        project.branches.list.side_effect = Exception("fail")
        collector = ag.BranchCollector()
        branches = collector.collect(project)
        self.assertEqual(branches, [])

class TestTagCollector(unittest.TestCase):
    @patch("AS_langgraphEnabler.gitlab")
    def test_collect_tags_handles_gitlab_list_error(self, mock_gitlab):
        project = MagicMock()
        project.tags.list.side_effect = mock_gitlab.exceptions.GitlabListError("fail")
        collector = ag.TagCollector()
        tags = collector.collect_tags(project)
        self.assertEqual(tags, [])
    def test_collect_tags_handles_exception(self):
        project = MagicMock()
        project.tags.list.side_effect = Exception("fail")
        collector = ag.TagCollector()
        tags = collector.collect_tags(project)
        self.assertEqual(tags, [])

class TestReportGenerator(unittest.TestCase):
    def test_generate_report(self):
        gen = ag.ReportGenerator()
        branches = [{"status": ag.BranchStatus.INACTIVE.value}]
        tags = [{"is_semver": False, "days_since": 100}]
        artifacts = [{"artifact_days_to_expire": 2}, {"artifact_days_to_expire": -1}]
        report = gen.generate(branches, tags, artifacts)
        self.assertIn("ramas_obsoletas", report)
        self.assertIn("tags_no_semver", report)
        self.assertIn("artefactos_por_expirar", report)
        self.assertEqual(len(report["ramas_obsoletas"]), 1)
        self.assertEqual(len(report["tags_no_semver"]), 1)
        self.assertEqual(len(report["artefactos_por_expirar"]), 1)
        self.assertEqual(len(report["artefactos_expirados"]), 1)

class TestIntelligentAnalyzer(unittest.TestCase):
    def test_analyze_no_llm(self):
        analyzer = ag.IntelligentAnalyzer(llm_client=None)
        state = {"branches": [], "tags": [], "artifacts": [], "maintenance_report": None, "project_ids": []}
        result = analyzer.analyze(state)
        self.assertIn("no disponible", result)

if __name__ == "__main__":
    unittest.main()
