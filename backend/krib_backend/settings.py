import os
import importlib.util
from pathlib import Path
from datetime import timedelta
from urllib.parse import parse_qsl, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

# Load env files explicitly so running Django from /backend or the repo root
# picks up the same configuration every time. In production we do NOT let a
# stray repo-checkout .env clobber the operator-supplied shell environment
# (the previous override=True caused `python manage.py check --deploy` to
# silently read dev values from a committed .env on the deploy host).
_dotenv_override = os.getenv("DJANGO_DEBUG", "0") == "1"
load_dotenv(PROJECT_ROOT / ".env", override=_dotenv_override)
load_dotenv(BASE_DIR / ".env", override=_dotenv_override)

HAS_DJANGO_CRONTAB = importlib.util.find_spec("django_crontab") is not None
HAS_WHITENOISE = importlib.util.find_spec("whitenoise") is not None


def _csv_env(name, default=""):
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


def _append_unique(items, value):
    if value and value not in items:
        items.append(value)


def _env_url_host(name):
    value = os.getenv(name, "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    return (parsed.hostname or "").strip()


def _env_url_origin(name):
    value = os.getenv(name, "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _mysql_options(query_options=None):
    query_options = query_options or {}
    options = {
        "charset": query_options.get("charset", os.getenv("MYSQL_CHARSET", "utf8mb4")).strip() or "utf8mb4",
    }

    ssl_enabled = query_options.get("ssl", "").strip().lower() in {
        "1", "true", "yes", "require", "required"}
    ssl_enabled = ssl_enabled or os.getenv("MYSQL_USE_SSL", "0") == "1"

    ssl = {}
    for env_name, key in (
        ("MYSQL_SSL_CA", "ca"),
        ("MYSQL_SSL_CERT", "cert"),
        ("MYSQL_SSL_KEY", "key"),
    ):
        value = os.getenv(env_name, "").strip()
        if value:
            ssl[key] = value
            ssl_enabled = True

    if ssl_enabled:
        options["ssl"] = ssl

    return options


def _default_mysql_config():
    host = os.getenv("MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    return {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("MYSQL_DATABASE", "krib_db").strip() or "krib_db",
            "USER": os.getenv("MYSQL_USER", "krib_user").strip() or "krib_user",
            "PASSWORD": os.getenv("MYSQL_PASSWORD", "krib_password"),
            "HOST": host,
            "PORT": os.getenv("MYSQL_PORT", "3307").strip() or "3307",
            "CONN_MAX_AGE": int(os.getenv("DJANGO_CONN_MAX_AGE", "60")),
            "OPTIONS": _mysql_options(),
        }
    }


def _database_config_from_env():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return _default_mysql_config()

    parsed = urlparse(database_url)
    query_options = dict(parse_qsl(parsed.query, keep_blank_values=True))
    engines = {
        "mysql": "django.db.backends.mysql",
        "mysql2": "django.db.backends.mysql",
        "mariadb": "django.db.backends.mysql",
        "sqlite": "django.db.backends.sqlite3",
    }
    engine = engines.get(parsed.scheme)
    if engine == "django.db.backends.sqlite3":
        sqlite_name = parsed.path[1:] if parsed.path.startswith(
            "/") else parsed.path
        return {"default": {"ENGINE": engine, "NAME": sqlite_name or BASE_DIR / "db.sqlite3"}}
    if engine == "django.db.backends.mysql":
        return {
            "default": {
                "ENGINE": engine,
                "NAME": parsed.path.lstrip("/"),
                "USER": parsed.username or "",
                "PASSWORD": parsed.password or "",
                "HOST": parsed.hostname or "",
                "PORT": str(parsed.port or "3307"),
                "CONN_MAX_AGE": int(os.getenv("DJANGO_CONN_MAX_AGE", "60")),
                "OPTIONS": _mysql_options(query_options),
            }
        }
    if not engine:
        raise ValueError(
            "Unsupported DATABASE_URL scheme. Use mysql://, mariadb://, or sqlite:///")


DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-secret-key"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG=0.")

# In production, fail boot if the DJANGO_SECRET_KEY is too short to be safe.
# Django uses it for cookie signing, password reset tokens, and CSRF tokens.
if not DEBUG and len(SECRET_KEY) < 32:
    raise RuntimeError("DJANGO_SECRET_KEY must be at least 32 characters long in production.")

# Webhook authenticity depends entirely on the IntaSend HMAC secret. In
# production we refuse to boot if it is missing or weak; this turns the
# previously-silent failure mode (anyone with the URL could potentially
# forge a webhook if signature verification was misconfigured) into a
# loud startup error.
INTASEND_WEBHOOK_SECRET_MIN_LENGTH = 32
_intasend_webhook_secret = os.getenv("INTASEND_WEBHOOK_SECRET", "").strip()
if not DEBUG:
    if not _intasend_webhook_secret:
        raise RuntimeError(
            "INTASEND_WEBHOOK_SECRET must be set in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    if len(_intasend_webhook_secret) < INTASEND_WEBHOOK_SECRET_MIN_LENGTH:
        raise RuntimeError(
            "INTASEND_WEBHOOK_SECRET must be at least "
            f"{INTASEND_WEBHOOK_SECRET_MIN_LENGTH} characters long in production."
        )

    # If Stripe is configured at all, the webhook secret MUST also be set,
    # otherwise the StripeWebhookView falls back to 503 at request time but
    # the operator never finds out until the first failed event lands.
    _stripe_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    _stripe_webhook = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if _stripe_key and not _stripe_webhook:
        raise RuntimeError(
            "STRIPE_WEBHOOK_SECRET is required whenever STRIPE_SECRET_KEY is set."
        )

ALLOWED_HOSTS = _csv_env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
for env_name in ("PUBLIC_BASE_URL", "FRONTEND_URL", "BACKEND_URL", "MPESA_CALLBACK_URL"):
    _append_unique(ALLOWED_HOSTS, _env_url_host(env_name))

INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    # token_blacklist powers server-side refresh-token invalidation. Without
    # it, a stolen refresh token stays valid until natural expiry; with it,
    # /api/auth/logout/ can revoke it immediately.
    "rest_framework_simplejwt.token_blacklist",
    "core",
]

if HAS_DJANGO_CRONTAB:
    INSTALLED_APPS.append("django_crontab")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

if HAS_WHITENOISE:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "krib_backend.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

WSGI_APPLICATION = "krib_backend.wsgi.application"

DATABASES = _database_config_from_env()

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DRF + JWT
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "login": "5/min",
        "register": "5/min",
        "password_reset": "3/min",
        "password_reset_confirm": "10/min",
        "stk_initiate": "10/min",
        "otp_verify": "5/minute",
        # Stop attackers from bypassing /api/auth/login/'s 5/min cap by
        # hammering the alternate SimpleJWT token endpoint at the same rate.
        "token_obtain": "5/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7"))),
    # Rotate the refresh token on every /api/token/refresh/ call and blacklist
    # the previous one. This means a leaked refresh token has a much smaller
    # usable window before the legitimate client rotates it out.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}


# Media files (uploads)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_DOCUMENT_MIME_TYPES = (
    "application/pdf",
    "image/jpeg",
    "image/png",
)
ALLOWED_IMAGE_MIME_TYPES = (
    "image/jpeg",
    "image/png",
)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")
# CALLBACK_PATH_SECRET was historically interpolated into MPESA_CALLBACK_URL but
# never enforced by any URL route, so it gave a false sense of "path secret"
# protection. The HMAC signature verification on the IntaSend webhook
# (INTASEND_WEBHOOK_SECRET) is the only legitimate gate. The env var is now
# ignored; the variable name is kept here for legacy boot scripts but does
# not change the callback URL.
_callback_base_url = (PUBLIC_BASE_URL or BACKEND_URL or "http://localhost:8000").rstrip("/")
MPESA_CALLBACK_URL = os.getenv(
    "MPESA_CALLBACK_URL",
    f"{_callback_base_url}/api/payments/mpesa/callback/",
).rstrip("/")
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "KRIB")
# Hours that must pass between updating LandlordSettings.payout_destination
# and being allowed to request a payout. Defends against session-hijack →
# update destination → immediate payout. 24h by default; can be lowered for
# staging/test runs via the env var.
LANDLORD_PAYOUT_COOLDOWN_HOURS = int(os.getenv("LANDLORD_PAYOUT_COOLDOWN_HOURS", "24"))

# Phase 2B: KRIB subscription billing rail (separate from rent collection).
# Charged to landlords for using the platform; payments flow to KRIB's own
# IntaSend account, not to landlords. Enforcement (suspending accounts) is
# explicitly DEFERRED — only the invoicing + reminder surface ships now.
SUBSCRIPTION_PER_UNIT_KES = int(os.getenv("SUBSCRIPTION_PER_UNIT_KES", "50"))
SUBSCRIPTION_FREE_TIER_THRESHOLD = int(os.getenv("SUBSCRIPTION_FREE_TIER_THRESHOLD", "5"))
SUBSCRIPTION_BILLING_DAY = int(os.getenv("SUBSCRIPTION_BILLING_DAY", "1"))
SUBSCRIPTION_GRACE_PERIOD_DAYS = int(os.getenv("SUBSCRIPTION_GRACE_PERIOD_DAYS", "7"))
SUBSCRIPTION_OVERDUE_DAYS = int(os.getenv("SUBSCRIPTION_OVERDUE_DAYS", "14"))
# Placeholder for a future phase. NEVER read by code in this phase — leaving the
# flag wired up means a later enforcement landing only has to flip the env var
# rather than re-introduce the setting.
SUBSCRIPTION_ENFORCEMENT_ENABLED = os.getenv(
    "SUBSCRIPTION_ENFORCEMENT_ENABLED", "0"
).strip().lower() in {"1", "true", "yes", "on"}

# Custody mode: KRIB holds landlord funds and initiates payouts.
# KRIB is a transaction monitor - custody mode is disabled by default.
# Set to "1" only if you explicitly want to enable the custody rail.
CUSTODY_MODE_ENABLED = os.getenv(
    "CUSTODY_MODE_ENABLED", "0"
).strip().lower() in {"1", "true", "yes", "on"}

# The currency the payment core compares incoming provider events against.
# IntaSend is fixed to KES, Stripe accepts whatever the PaymentIntent was
# created in (we currency-pin via STRIPE_CURRENCY), PayPal mirrors
# PAYPAL_CURRENCY. Set this to whatever the merchant account uses.
DEFAULT_PAYMENT_CURRENCY = os.getenv("DEFAULT_PAYMENT_CURRENCY", "KES").upper()
SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "")
BUSINESS_ADDRESS = os.getenv("BUSINESS_ADDRESS", "")

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "0") == "1"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@krib.local")

# CORS / CSRF
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = _csv_env("DJANGO_CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = _csv_env("DJANGO_CSRF_TRUSTED_ORIGINS")
for env_name in ("PUBLIC_BASE_URL", "FRONTEND_URL", "BACKEND_URL", "MPESA_CALLBACK_URL"):
    origin = _env_url_origin(env_name)
    _append_unique(CORS_ALLOWED_ORIGINS, origin)
    _append_unique(CSRF_TRUSTED_ORIGINS, origin)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Default to redirecting HTTP→HTTPS in production. Operators must explicitly
# set DJANGO_SECURE_SSL_REDIRECT=0 to opt out (e.g. behind a TLS-terminating
# proxy that already enforces HTTPS). The previous default was "off until
# someone remembers to flip it", which is the wrong way around.
SECURE_SSL_REDIRECT = (not DEBUG) and os.getenv("DJANGO_SECURE_SSL_REDIRECT", "1") != "0"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
}

if HAS_DJANGO_CRONTAB:
    CRONJOBS = [
        ("0 * * * *", "django.core.management.call_command",
         ["unlock_balances"]),
        ("0 6 * * *", "django.core.management.call_command",
         ["check_arrears"]),
    ]
