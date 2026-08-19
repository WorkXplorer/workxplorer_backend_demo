import os
from .env_loader import env_loader

# Determine environment
environment = os.getenv("DJANGO_ENVIRONMENT", "development")

# Validate required variables for current environment
env_loader.validate_required_vars(environment)

# Import appropriate settings
if environment == "production":
    from .production import *
elif environment == "demo":
    from .demo import *
else:
    from .development import *
