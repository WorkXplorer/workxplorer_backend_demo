from pathlib import Path

# Get BASE_DIR from the path resolution
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/staticfiles/"
MEDIA_URL = "/mediafiles/"
STATIC_ROOT = str(BASE_DIR / "staticfiles")
MEDIA_ROOT = str(BASE_DIR / "mediafiles")
