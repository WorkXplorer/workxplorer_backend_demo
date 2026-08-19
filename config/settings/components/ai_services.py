"""
AI Services Configuration

Configuration for external AI service integrations.
"""

from config.settings.env_loader import env_loader

# AI Provider Configuration
AI_API_KEY = env_loader.get_env("AI_API_KEY", default=None)
AI_MODEL = env_loader.get_env("AI_MODEL", default=None)
AI_API_BASE_URL = env_loader.get_env("AI_API_BASE_URL", default=None)

# GitHub API Configuration
GITHUB_TOKEN = env_loader.get_env("GITHUB_TOKEN", default=None)
