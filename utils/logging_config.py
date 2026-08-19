import os
import gzip
import shutil
import logging

from pathlib import Path
from logging.handlers import TimedRotatingFileHandler


BASE_LOG_DIR = Path("logs")

# URL prefix to log category mapping
LOG_ROUTE_MAP = {
    "/api/v1/vacancies/": "vacancies",
    "/api/v1/users/": "custom_users",
    "/api/v1/auth/": "custom_users",
    "/api/v1/profiles/": "companies",
    "/api/v1/applications/": "applications",
}


class CompressedTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Custom handler that compresses rotated log files to .gz format"""

    def rotator(self, source, dest):
        """Compress the rotated log file"""
        with open(source, "rb") as f_in:
            with gzip.open(f"{dest}.gz", "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)


def _ensure_dir(path):
    """Create directory if it doesn't exist."""
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o755)
    except OSError as e:
        print(f"Error creating log directory {path}: {e}")
        raise


def _create_logger(name, log_file):
    """Create a logger with daily rotation and .gz compression."""
    logger = logging.getLogger(name)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.propagate = False

    if logger.handlers:
        logger.handlers.clear()

    _ensure_dir(log_file.parent)

    handler = CompressedTimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


def setup_request_logger():
    """Configure and return the global request logger with daily rotation."""
    return _create_logger("api_requests", BASE_LOG_DIR / "requests" / "requests.log")


def setup_category_loggers():
    """Configure and return per-category loggers for specific API endpoints."""
    categories = {
        "vacancies": "vacancies",
        "custom_users": "custom_users",
        "companies": "companies",
        "applications": "applications",
    }
    loggers = {}
    for key, folder in categories.items():
        loggers[key] = _create_logger(
            f"api_{key}", BASE_LOG_DIR / folder / f"{folder}.log"
        )
    return loggers


def get_log_category(path):
    """Determine which log category a request path belongs to."""
    for prefix, category in LOG_ROUTE_MAP.items():
        if path.startswith(prefix):
            return category
    return None
