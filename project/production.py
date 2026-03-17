from .settings import *  # noqa: F401,F403
import dj_database_url

DEBUG = False

DATABASES = {
    'default': dj_database_url.config(default=os.getenv('DATABASE_URL'))
}
