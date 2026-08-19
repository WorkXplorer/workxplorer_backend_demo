# config/settings/env_loader.py
import os
from typing import Optional
from dotenv import load_dotenv


class EnvironmentLoader:
    def __init__(self):
        self._load_environment_files()
        self._required_vars = {
            "production": [
                "SECRET_KEY",
                "DB_NAME",
                "DB_USER",
                "DB_PASSWORD",
                "DB_HOST",
                "DB_PORT",
                "JWT_SECRET_KEY",
            ],
            "demo": [ 
                "SECRET_KEY",
                "DB_NAME",
                "DB_USER",
                "DB_PASSWORD",
                "DB_HOST",
                "DB_PORT",
                "JWT_SECRET_KEY",
            ],
            "development": ["SECRET_KEY", "JWT_SECRET_KEY"],
        }

    def _load_environment_files(self):
        # Determine environment first
        environment = os.getenv("DJANGO_ENVIRONMENT", "development")

        # Load environment-specific file based on your naming convention
        if environment == "production":
            env_file = ".env.production"
        elif environment == "demo":
            env_file = ".env.demo"
        else:
            env_file = ".env.development"

        # Load the specific environment file.
        # override=False ensures already-set env vars (e.g. from Docker's
        # `environment:` block) take precedence over values in the .env file.
        # This prevents the .env file from undoing critical Docker overrides
        # such as DJANGO_ENVIRONMENT.
        load_dotenv(env_file, override=False)

    def get_env(
        self, key: str, default: Optional[str] = None, required: bool = False
    ) -> Optional[str]:
        value = os.getenv(key, default)
        if required and not value:
            raise ValueError(f"Required environment variable '{key}' is not set")
        return value

    def validate_required_vars(self, environment: str):
        missing = []
        for var in self._required_vars.get(environment, []):
            if not os.getenv(var):
                missing.append(var)

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


# Global instance
env_loader = EnvironmentLoader()
