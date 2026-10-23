"""Date-range helpers for reports.

Django's ``__date`` lookup on MySQL/MariaDB uses ``CONVERT_TZ`` when ``USE_TZ``
is enabled. If the database's timezone tables are not loaded, that expression
returns ``NULL`` and every report silently shows zero. cPanel MariaDB servers
do not always have those tables populated, so reports use explicit UTC
boundaries instead.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.utils import timezone


def local_day_bounds(day: date | None = None) -> tuple[datetime, datetime]:
    """Return the half-open UTC range ``[start, end)`` for a local calendar day."""

    day = day or timezone.localdate()
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = timezone.make_aware(
        datetime.combine(day + timedelta(days=1), time.min), tz
    )
    return start, end


def local_day_range(day: date | None = None) -> dict[str, datetime]:
    """Build ``__gte``/``__lt`` kwargs for a local day range."""

    start, end = local_day_bounds(day)
    return {"gte": start, "lt": end}
