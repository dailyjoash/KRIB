$env:DJANGO_SETTINGS_MODULE = "krib_backend.settings_test"
python manage.py test core.tests.test_mvp_hardening --verbosity=2
