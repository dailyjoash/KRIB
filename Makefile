test:
	cd backend && python manage.py test \
	core.tests.test_mvp_hardening \
	--settings=krib_backend.settings_test \
	--verbosity=2
