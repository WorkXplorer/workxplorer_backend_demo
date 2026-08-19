"""
Tests for GitHub data fetching service.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.resumes.services.github_service import (
    parse_github_username,
    fetch_github_data,
    format_github_context_for_prompt,
)


class ParseGithubUsernameTests(SimpleTestCase):
    """Tests for parse_github_username function."""

    def test_extracts_username_from_https_url(self):
        self.assertEqual(parse_github_username("https://github.com/torvalds"), "torvalds")

    def test_extracts_username_from_http_url(self):
        self.assertEqual(parse_github_username("http://github.com/user123"), "user123")

    def test_extracts_username_without_protocol(self):
        self.assertEqual(parse_github_username("github.com/my-user"), "my-user")

    def test_extracts_username_with_trailing_slash(self):
        self.assertEqual(parse_github_username("https://github.com/user123/"), "user123")

    def test_returns_none_for_empty_url(self):
        self.assertIsNone(parse_github_username(""))

    def test_returns_none_for_invalid_url(self):
        self.assertIsNone(parse_github_username("https://google.com"))

    def test_returns_none_for_github_root(self):
        self.assertIsNone(parse_github_username("https://github.com/"))

    def test_extracts_username_with_hyphens(self):
        self.assertEqual(parse_github_username("github.com/user-name-dev"), "user-name-dev")


class FormatGithubContextForPromptTests(SimpleTestCase):
    """Tests for format_github_context_for_prompt."""

    def test_returns_empty_for_failed_request(self):
        result = format_github_context_for_prompt({
            "success": False,
            "data": None,
            "error": "Not found",
        })
        self.assertEqual(result, "")

    def test_returns_empty_for_missing_data(self):
        result = format_github_context_for_prompt({
            "success": True,
            "data": None,
            "error": None,
        })
        self.assertEqual(result, "")

    def test_formats_basic_data(self):
        github_data = {
            "success": True,
            "data": {
                "username": "testuser",
                "public_repos": 10,
                "followers": 5,
                "total_stars": 20,
                "total_forks": 3,
                "primary_language": "Python",
                "repositories": [
                    {
                        "name": "cool-project",
                        "description": "A cool project",
                        "language": "Python",
                        "stars": 15,
                        "forks": 2,
                    },
                    {
                        "name": "utils-lib",
                        "description": None,
                        "language": "JavaScript",
                        "stars": 5,
                        "forks": 1,
                    },
                ],
            },
            "error": None,
        }
        result = format_github_context_for_prompt(github_data)
        self.assertIn("Username: testuser", result)
        self.assertIn("Public repositories: 10", result)
        self.assertIn("Followers: 5", result)
        self.assertIn("Total stars across repos: 20", result)
        self.assertIn("Primary language: Python", result)
        self.assertIn("cool-project [Python]", result)
        self.assertIn("utils-lib [JavaScript]", result)
        self.assertIn("A cool project", result)

    def test_formats_data_without_primary_language(self):
        github_data = {
            "success": True,
            "data": {
                "username": "testuser",
                "public_repos": 3,
                "followers": 0,
                "total_stars": 0,
                "total_forks": 0,
                "primary_language": None,
                "repositories": [],
            },
            "error": None,
        }
        result = format_github_context_for_prompt(github_data)
        self.assertIn("Username: testuser", result)
        self.assertNotIn("Primary language", result)


class FetchGithubDataTests(SimpleTestCase):
    """Tests for fetch_github_data with mocked PyGithub."""

    def setUp(self):
        self.github_url = "https://github.com/testuser"
        self.mock_user = MagicMock()
        self.mock_user.public_repos = 5
        self.mock_user.followers = 10

        self.mock_repo1 = MagicMock()
        self.mock_repo1.fork = False
        self.mock_repo1.name = "awesome-project"
        self.mock_repo1.description = "An awesome project"
        self.mock_repo1.language = "Python"
        self.mock_repo1.stargazers_count = 25
        self.mock_repo1.forks_count = 3

        self.mock_repo2 = MagicMock()
        self.mock_repo2.fork = False
        self.mock_repo2.name = "dotfiles"
        self.mock_repo2.description = None
        self.mock_repo2.language = "Shell"
        self.mock_repo2.stargazers_count = 5
        self.mock_repo2.forks_count = 0

        self.mock_repo3 = MagicMock()
        self.mock_repo3.fork = True  # Forked repo - should be skipped
        self.mock_repo3.name = "forked-project"

        self.mock_user.get_repos.return_value = [
            self.mock_repo1,
            self.mock_repo2,
            self.mock_repo3,
        ]

    @patch("apps.resumes.services.github_service.Github")
    @patch("apps.resumes.services.github_service.settings")
    def test_fetch_success(self, mock_settings, mock_github_class):
        mock_settings.GITHUB_TOKEN = None
        mock_github = mock_github_class.return_value
        mock_github.get_user.return_value = self.mock_user

        result = fetch_github_data(self.github_url)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["username"], "testuser")
        self.assertEqual(result["data"]["public_repos"], 5)
        self.assertEqual(result["data"]["followers"], 10)
        self.assertEqual(result["data"]["total_stars"], 30)
        self.assertEqual(result["data"]["total_forks"], 3)
        self.assertEqual(result["data"]["primary_language"], "Python")
        self.assertEqual(len(result["data"]["repositories"]), 2)
        repo_names = [r["name"] for r in result["data"]["repositories"]]
        self.assertIn("awesome-project", repo_names)
        self.assertIn("dotfiles", repo_names)
        self.assertNotIn("forked-project", repo_names)
        self.assertIsNone(result["error"])

    @patch("apps.resumes.services.github_service.Github")
    @patch("apps.resumes.services.github_service.settings")
    def test_fetch_with_token(self, mock_settings, mock_github_class):
        mock_settings.GITHUB_TOKEN = "ghp_testtoken123"
        mock_github = mock_github_class.return_value
        mock_github.get_user.return_value = self.mock_user

        fetch_github_data(self.github_url)

        mock_github_class.assert_called_once_with("ghp_testtoken123")

    def test_returns_error_for_invalid_url(self):
        result = fetch_github_data("not-a-github-url")
        self.assertFalse(result["success"])
        self.assertIn("Could not parse", result["error"])

    @patch("apps.resumes.services.github_service.Github")
    @patch("apps.resumes.services.github_service.settings")
    def test_returns_error_for_rate_limit(self, mock_settings, mock_github_class):
        mock_settings.GITHUB_TOKEN = None
        mock_github = mock_github_class.return_value
        mock_github.get_user.side_effect = __import__(
            "github",
            fromlist=["RateLimitExceededException"],
        ).RateLimitExceededException(403, "rate limit")

        result = fetch_github_data(self.github_url)

        self.assertFalse(result["success"])
        self.assertIn("rate limit", result["error"])

    @patch("apps.resumes.services.github_service.Github")
    @patch("apps.resumes.services.github_service.settings")
    def test_returns_error_for_404(self, mock_settings, mock_github_class):
        mock_settings.GITHUB_TOKEN = None
        mock_github = mock_github_class.return_value

        from github import GithubException
        mock_github.get_user.side_effect = GithubException(404, "Not Found")

        result = fetch_github_data(self.github_url)

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())
