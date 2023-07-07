from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

DEBUG = False


# TODO: remove
SECRET_KEY = "dummy"
STATIC_ROOT = BASE_DIR.parents[1] / "www/static"
MEDIA_ROOT = BASE_DIR.parents[1] / "www/media"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


INTERNAL_IPS = [
    "0.0.0.0",
    "127.0.0.1",
]

ALLOWED_HOSTS = [
    "0.0.0.0",
    "127.0.0.1",
    "localhost",
]

ADMINS = [
    "gregory@stopdesign.ru",
]


# Application definition
INSTALLED_APPS = [
    # django
    "admin_interface",
    "colorfield",

    "django_admin_filters",
    "debug_toolbar",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # project
    "project",
    "main",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # "main.middleware.login_required.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

ROOT_URLCONF = "project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["project/templates", "main/templates", "admin_interface/templates"],
        # "DIRS": ["templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'


# STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

# Collect static files from the frontend build directory (if available)
# STATICFILES_DIRS = []
# front_dist_path = BASE_DIR.parents[1] / "static"
# if front_dist_path.exists():
#     STATICFILES_DIRS.append(front_dist_path)
# print("BASE_DIR", BASE_DIR)
# print("STATICFILES_DIRS", STATICFILES_DIRS)
# print("STATIC_ROOT", STATIC_ROOT)

WSGI_APPLICATION = "project.wsgi.application"


# AUTH_USER_MODEL = "main.User"
PASSWORD_RESET_TIMEOUT_DAYS = 1


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
USE_I18N = False
USE_L10N = False
USE_TZ = True
TIME_ZONE = "UTC"

DATE_FORMAT = 'd E Y'
SHORT_DATE_FORMAT = 'd.m.Y'
DATETIME_FORMAT = 'd.m.Y, H:i:s'
SHORT_DATETIME_FORMAT = 'd.m.Y, H:i:s'

STATIC_URL = "/static/"
MEDIA_URL = "/media/"

APPEND_SLASH = False

CORS_ALLOW_ALL_ORIGINS = True

NO_COLOR = True
