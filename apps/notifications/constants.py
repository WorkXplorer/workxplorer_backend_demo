"""
Constants for the notifications app.
"""

# Cache key patterns
CACHE_KEY_UNREAD_COUNT = "unread_count_user_{user_id}"
CACHE_KEY_NOTIFICATIONS_PATTERN = "notifications_user_{user_id}_*"
CACHE_KEY_NOTIFICATIONS_VERSION = "notifications_user_{user_id}_version"

# Cache timeouts (in seconds)
CACHE_TIMEOUT_NOTIFICATIONS = 300  # 5 minutes

# Pagination defaults
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Job timeout (in seconds)
DEFAULT_JOB_TIMEOUT = 360
