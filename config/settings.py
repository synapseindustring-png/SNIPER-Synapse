import os
from pathlib import Path
from urllib.parse import unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DATA_DIR = Path(os.getenv("TEMP_DATA_DIR", "/tmp/synapse-sniper"))
CNPJ_SOURCE_BASE_URL = os.getenv("CNPJ_SOURCE_BASE_URL", "").strip()
CNPJ_WEBDAV_TOKEN = os.getenv("CNPJ_WEBDAV_TOKEN", "").strip()
CNPJ_MANIFEST_MAX_BYTES = int(os.getenv("CNPJ_MANIFEST_MAX_BYTES", str(5 * 1024**2)))
CNPJ_MAX_TEMP_BYTES = int(os.getenv("CNPJ_MAX_TEMP_BYTES", str(3 * 1024**3)))
CNPJ_MIN_FREE_BYTES = int(os.getenv("CNPJ_MIN_FREE_BYTES", str(5 * 1024**3)))
CNPJ_DOWNLOAD_TIMEOUT_SECONDS = int(os.getenv("CNPJ_DOWNLOAD_TIMEOUT_SECONDS", "120"))
CNPJ_PREVIEW_MAX_RESULTS = int(os.getenv("CNPJ_PREVIEW_MAX_RESULTS", "500"))
CNPJ_MAX_PERSISTED_MATCHES = int(os.getenv("CNPJ_MAX_PERSISTED_MATCHES", "10000"))
CNPJ_TEMP_MAX_AGE_SECONDS = int(os.getenv("CNPJ_TEMP_MAX_AGE_SECONDS", "21600"))
CRAWLER_USER_AGENT = os.getenv("CRAWLER_USER_AGENT", "SynapseSniper/0.1").strip()
CRAWLER_CONTACT = os.getenv("CRAWLER_CONTACT", "").strip()
CRAWLER_TIMEOUT_SECONDS = int(os.getenv("CRAWLER_TIMEOUT_SECONDS", "20"))
CRAWLER_MAX_BYTES = int(os.getenv("CRAWLER_MAX_BYTES", "5000000"))
CRAWLER_MAX_TEXT_CHARS = int(os.getenv("CRAWLER_MAX_TEXT_CHARS", "200000"))
CRAWLER_MAX_REDIRECTS = int(os.getenv("CRAWLER_MAX_REDIRECTS", "3"))
CRAWLER_MAX_PAGES = int(os.getenv("CRAWLER_MAX_PAGES", "5"))
JOB_POSTING_MAX_AGE_DAYS = int(os.getenv("JOB_POSTING_MAX_AGE_DAYS", "365"))
JOBS_FIXTURE_ROOT = Path(os.getenv("JOBS_FIXTURE_ROOT", str(BASE_DIR / "fixtures" / "jobs")))
JOBS_MAX_PAGES = int(os.getenv("JOBS_MAX_PAGES", "2"))
JOBS_MAX_RESULTS = int(os.getenv("JOBS_MAX_RESULTS", "100"))
JOBS_MAX_RESPONSE_BYTES = int(os.getenv("JOBS_MAX_RESPONSE_BYTES", "1000000"))


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


JOBS_ADAPTER_ENABLED = env_bool("JOBS_ADAPTER_ENABLED", False)
CNPJ_FULL_ENABLED = env_bool("CNPJ_FULL_ENABLED", False)


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key")
if not DEBUG and SECRET_KEY == "dev-only-insecure-secret-key":
    raise RuntimeError("DJANGO_SECRET_KEY must be configured when DJANGO_DEBUG=false")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.jobs",
    "apps.companies",
    "apps.discovery",
    "apps.sources",
    "apps.crawler",
    "apps.signals",
    "apps.scoring",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]


def database_config() -> dict:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL must use postgresql://")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": parsed.port or 5432,
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }


DATABASES = {"default": database_config()}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = os.getenv("APP_TIME_ZONE", "America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SECURE_HSTS_SECONDS = int(
    os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "config.logging.JsonFormatter"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
