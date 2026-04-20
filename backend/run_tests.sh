#!/bin/bash
DJANGO_SETTINGS_MODULE=krib_backend.settings_test \
python manage.py migrate --run-syncdb 2>/dev/null
DJANGO_SETTINGS_MODULE=krib_backend.settings_test \
python manage.py test core.tests.test_mvp_hardening --verbosity=2
