from .settings import *


# Override database for local test runs only
# Uses SQLite so no CREATEDB privilege is needed
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }
}

# Faster password hashing in tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Effectively disable throttling in tests by raising the per-scope rate to a
# number we will never hit. Clearing the dict outright triggers
# ImproperlyConfigured because the named scope must still be registered.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "login": "1000000/min",
        "register": "1000000/min",
        "password_reset": "1000000/min",
        "password_reset_confirm": "1000000/min",
        "stk_initiate": "1000000/min",
        "otp_verify": "1000000/min",
        "token_obtain": "1000000/min",
    },
}

# Disable cron during tests
CRONJOBS = []

# Silence migration output during tests
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


# Do not add MIGRATION_MODULES here - keep real migrations
# so the SQLite schema matches production models exactly
