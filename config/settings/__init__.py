"""Settings selector.

``DJANGO_SETTINGS_MODULE=config.settings`` remains the cPanel/Passenger entry
point. The concrete settings module is selected here so the deployment path does
not need to change while development and production stay separated.

Defaults to production. Set ``DJANGO_ENV=development`` locally or
``DJANGO_ENV=test`` in CI/test commands.
"""

from __future__ import annotations

import os
import sys

from config.env import load_env

load_env()

_environment = os.getenv("DJANGO_ENV", "").strip().lower()
if not _environment:
    if len(sys.argv) > 1 and sys.argv[1] in {"test", "testserver"}:
        _environment = "test"
    elif os.getenv("DJANGO_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}:
        _environment = "development"
    else:
        _environment = "production"

if _environment in {"dev", "development", "local"}:
    from .dev import *  # noqa: F401,F403
elif _environment in {"test", "testing"}:
    from .test import *  # noqa: F401,F403
else:
    from .prod import *  # noqa: F401,F403
