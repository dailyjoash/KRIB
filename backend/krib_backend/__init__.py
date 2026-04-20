import pymysql

# Django 6 checks the MySQLdb version tuple before importing the backend.
# PyMySQL still reports the older mysqlclient-compatible compatibility version
# by default, so we advertise a modern equivalent before installing the shim.
pymysql.version_info = (2, 2, 1, "final", 0)
pymysql.__version__ = "2.2.1"

# Let Django's MySQL backend use the pure-Python driver in local Windows setups
# and slim containers without needing mysqlclient system packages.
pymysql.install_as_MySQLdb()
