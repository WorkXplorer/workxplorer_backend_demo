import os
from .cache import REDIS_URL

RQ_QUEUES = {
    "default": {
        "URL": REDIS_URL,
        "DEFAULT_TIMEOUT": 500,
    },
    "high": {
        "URL": REDIS_URL,
        "DEFAULT_TIMEOUT": 300,
    },
    "low": {
        "URL": REDIS_URL,
        "DEFAULT_TIMEOUT": 900,
    },
}

RQ_SHOW_ADMIN_LINK = True
RUN_SCHEDULER = True

# Job Queue Settings
# Admin email addresses for receiving alerts when jobs exceed retry limits
ADMIN_ALERT_EMAILS = os.environ.get("ADMIN_ALERT_EMAILS", "").split(",")
ADMIN_ALERT_EMAILS = [email.strip() for email in ADMIN_ALERT_EMAILS if email.strip()]

# Maximum retries before sending alert (default: 5)
JOB_QUEUE_MAX_RETRIES = int(os.environ.get("JOB_QUEUE_MAX_RETRIES", "5"))

# Days to keep completed jobs before cleanup (default: 30)
JOB_QUEUE_CLEANUP_DAYS = int(os.environ.get("JOB_QUEUE_CLEANUP_DAYS", "30"))

# Interval for checking and cleaning up old jobs (in seconds, default: 24 hours)
HR_ANALYTICS_INTERVAL = int(os.environ.get("HR_ANALYTICS_INTERVAL", "14400"))  # Default to 4 hours (14400 seconds)

# Interval for EduPartner analytics (in seconds, default: 24 hours)
EDUPARTNER_INTERVAL = int(os.environ.get("EDUPARTNER_INTERVAL", "86400"))  # Default to 24 hours (86400 seconds)

# Cron for the daily passive-skill AI validation job. Evaluated in UTC by
# rq-scheduler; 22:00 UTC == 03:00 Asia/Tashkent (fixed UTC+5, no DST).
SKILL_VALIDATION_CRON = os.environ.get("SKILL_VALIDATION_CRON", "0 22 * * *")

# Daily job-application report pushed to the Telegram group. Evaluated in UTC
# by rq-scheduler; 04:00 UTC == 09:00 Asia/Tashkent (fixed UTC+5, no DST).
DAILY_APPLICATION_REPORT_CRON = os.environ.get("DAILY_APPLICATION_REPORT_CRON", "0 4 * * *")

# Set to "false" to stop registering the daily report job (e.g. on demo/dev).
DAILY_APPLICATION_REPORT_ENABLED = os.environ.get(
    "DAILY_APPLICATION_REPORT_ENABLED", "true"
).lower() not in ("false", "0", "no")

# How many companies the report lists by name before folding the rest into an
# "and N more" line.
DAILY_APPLICATION_REPORT_TOP_COMPANIES = int(
    os.environ.get("DAILY_APPLICATION_REPORT_TOP_COMPANIES", "5")
)

# Same, for the per-university new-signup list in the same report.
DAILY_APPLICATION_REPORT_TOP_UNIVERSITIES = int(
    os.environ.get("DAILY_APPLICATION_REPORT_TOP_UNIVERSITIES", "5")
)

# Max skills a single user may submit within a rolling hour.
MAX_SKILLS_CREATED_PER_HOUR = int(os.environ.get("MAX_SKILLS_CREATED_PER_HOUR", "5"))
