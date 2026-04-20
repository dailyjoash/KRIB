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
