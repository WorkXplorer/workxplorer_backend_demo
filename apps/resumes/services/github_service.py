"""
GitHub profile data fetching service.

Provides functionality to fetch candidate GitHub profile data
using the PyGithub library for integration into AI resume generation.
"""

import logging
import re
import uuid
from typing import Optional

from django.conf import settings
from github import Github, GithubException, RateLimitExceededException

logger = logging.getLogger(__name__)


def parse_github_username(github_url: str) -> Optional[str]:
    """
    Extract GitHub username from a profile URL.

    Args:
        github_url: GitHub profile URL (e.g., github.com/username)

    Returns:
        GitHub username string or None
    """
    if not github_url:
        return None
    match = re.search(r'github\.com/([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)', github_url)
    if match:
        return match.group(1)
    return None


def fetch_github_data(github_url: str) -> dict:
    """
    Fetch GitHub profile data for a candidate.

    Uses PyGithub with optional GITHUB_TOKEN for authenticated access
    (5000 requests/hour vs 60 requests/hour unauthenticated).

    Args:
        github_url: GitHub profile URL

    Returns:
        Dict with structured GitHub profile data:
        {
            "success": bool,
            "data": {
                "username": str,
                "public_repos": int,
                "followers": int,
                "total_stars": int,
                "total_forks": int,
                "primary_language": str or None,
                "repositories": [
                    {
                        "name": str,
                        "description": str or None,
                        "language": str or None,
                        "stars": int,
                        "forks": int,
                    },
                    ...
                ],
            },
            "error": str or None,
        }
    """
    username = parse_github_username(github_url)
    if not username:
        return {"success": False, "data": None, "error": "Could not parse GitHub username from URL."}

    try:
        github_token = getattr(settings, 'GITHUB_TOKEN', None)
        g = Github(github_token) if github_token else Github()

        user = g.get_user(username)

        # Limit to top 50 repos to avoid performance issues with users who have many repos
        MAX_REPOS = 50
        repos = user.get_repos()[:MAX_REPOS]
        repo_list = []
        total_stars = 0
        total_forks = 0
        language_counts = {}

        for repo in repos:
            if repo.fork:
                continue
            stars = repo.stargazers_count
            forks = repo.forks_count
            total_stars += stars
            total_forks += forks

            if repo.language:
                language_counts[repo.language] = language_counts.get(repo.language, 0) + 1

            repo_list.append({
                "name": repo.name,
                "description": repo.description,
                "language": repo.language,
                "stars": stars,
                "forks": forks,
            })

        repo_list.sort(key=lambda r: r["stars"], reverse=True)

        top_repos = repo_list[:10]
        primary_language = max(language_counts, key=language_counts.get) if language_counts else None

        return {
            "success": True,
            "data": {
                "username": username,
                "public_repos": user.public_repos,
                "followers": user.followers,
                "total_stars": total_stars,
                "total_forks": total_forks,
                "primary_language": primary_language,
                "repositories": top_repos,
            },
            "error": None,
        }

    except RateLimitExceededException:
        logger.warning(f"GitHub API rate limit exceeded for user {username}")
        return {"success": False, "data": None, "error": "GitHub API rate limit exceeded. Try again later."}
    except GithubException as e:
        if e.status == 404:
            return {"success": False, "data": None, "error": f"GitHub user '{username}' not found."}
        error_ref = str(uuid.uuid4())[:8]
        logger.error(f"[Ref: {error_ref}] GitHub API error for user {username}: {e}")
        return {"success": False, "data": None, "error": f"GitHub API error: {str(e)} (Ref: {error_ref})"}
    except Exception as e:
        error_ref = str(uuid.uuid4())[:8]
        logger.error(f"[Ref: {error_ref}] Unexpected error fetching GitHub data for {username}: {e}")
        return {"success": False, "data": None, "error": f"Failed to fetch GitHub profile data. (Ref: {error_ref})"}


def format_github_context_for_prompt(github_data: dict) -> str:
    """
    Format GitHub data into a text block for the AI prompt.

    Args:
        github_data: Data returned by fetch_github_data()

    Returns:
        Formatted string for injection into the AI prompt
    """
    if not github_data.get("success") or not github_data.get("data"):
        return ""

    data = github_data["data"]
    lines = []
    lines.append(f"Username: {data['username']}")
    lines.append(f"Public repositories: {data['public_repos']}")
    lines.append(f"Followers: {data['followers']}")
    lines.append(f"Total stars across repos: {data['total_stars']}")
    lines.append(f"Total forks across repos: {data['total_forks']}")
    if data.get("primary_language"):
        lines.append(f"Primary language: {data['primary_language']}")

    repos = data.get("repositories", [])
    if repos:
        lines.append("\nTop repositories:")
        for i, repo in enumerate(repos, 1):
            desc = f" - {repo['description']}" if repo.get("description") else ""
            lang = f" [{repo['language']}]" if repo.get("language") else ""
            lines.append(
                f"  {i}. {repo['name']}{lang} (Stars: {repo['stars']}, Forks: {repo['forks']}){desc}"
            )

    return "\n".join(lines)
