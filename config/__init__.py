"""Project package.

cPanel/CloudLinux commonly lacks a compiler for ``mysqlclient``. PyMySQL is a
pure-Python driver and is installed as the MySQLdb compatibility layer when it
is available. Importing this package must not fail on SQLite-only installs.
"""

from __future__ import annotations

try:  # pragma: no cover - depends on the installed extras
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:  # pragma: no cover
    pass
