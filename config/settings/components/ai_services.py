"""
AI Services Configuration

Configuration for external AI service integrations.
"""

from config.settings.env_loader import env_loader

# Groq Cloud API Configuration
GROQ_API_KEY = env_loader.get_env("GROQ_API_KEY", default=None)
GROQ_MODEL = env_loader.get_env("GROQ_MODEL", default="qwen/qwen3-32b")

# GitHub API Configuration
GITHUB_TOKEN = env_loader.get_env("GITHUB_TOKEN", default=None)
