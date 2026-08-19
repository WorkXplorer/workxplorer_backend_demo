# ================== Validation Settings ==================
VALIDATION_MAX_LENGTHS = {
    "default": 1000,
    "text_field": 5000,
    "email": 254,
    "url": 2000,
    "phone": 20,
    "username": 50,
    "password": 128,
}

# ================== File Upload Settings ==================
ALLOWED_FILE_EXTENSIONS = [
    "jpg",
    "jpeg",
    "png",
    "pdf",
    "doc",
    "docx",
    "zip",
]
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
VALIDATION_SKIP_PATHS = [
    "/admin/",
    "/dashboard-admin-wxplr/",
    "/static/",
    "/media/",
    "/swagger",
    "/redoc",
    "/api/schema",
]
