from .settings import *  # noqa: F401,F403
import dj_database_url

DEBUG = False

DATABASES = {
    'default': dj_database_url.config(default=os.getenv('DATABASE_URL'))
}

# Production CORS — allow the deployed frontend origin
FRONTEND_URL = os.getenv('FRONTEND_URL', '').rstrip('/')
CORS_ALLOWED_ORIGINS = [
    origin for origin in [
        FRONTEND_URL,
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ] if origin
]
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ['X-AI-Response-Text']
