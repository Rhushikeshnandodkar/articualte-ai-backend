from .settings import *  # noqa: F401,F403
import dj_database_url
import os

DEBUG = True

DATABASES = {
    'default': dj_database_url.config(default=os.getenv('DATABASE_URL'))
}

# Resend for email (Render blocks SMTP). Set RESEND_API_KEY in env.
# Get key at https://resend.com/api-keys | Use onboarding@resend.dev for testing
_resend_key = os.getenv("RESEND_API_KEY", "").strip()
if _resend_key:
    RESEND_API_KEY = _resend_key
    RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev").strip() or "onboarding@resend.dev"

# Production CORS: use explicit origins to avoid "CORS Missing Allow Origin" with credentials.
# Set CORS_ALLOWED_ORIGINS (comma-separated) or FRONTEND_URL in env.
# Example: CORS_ALLOWED_ORIGINS=https://app.example.com  OR  FRONTEND_URL=https://app.example.com
_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
if not _cors_origins:
    _frontend = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    if _frontend:
        _cors_origins = _frontend
if _cors_origins:
    origins = list({o.strip().rstrip("/") for o in _cors_origins.split(",") if o.strip()})
    # Keep localhost for local testing with production settings
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        if origin not in origins:
            origins.append(origin)
    CORS_ALLOWED_ORIGINS = origins
    CORS_ALLOW_ALL_ORIGINS = False
else:
    CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ['X-AI-Response-Text']
