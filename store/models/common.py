"""Shared helpers for the model package."""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


def money_field(**kwargs):
    """Exact Toman amount.

    Prices are stored as whole Toman. ``DecimalField`` (rather than a float or
    an unbounded integer) keeps every calculation exact and makes the unit
    explicit to readers and to the database.
    """

    defaults = {
        "max_digits": 14,
        "decimal_places": 0,
        "validators": [MinValueValidator(Decimal("0"))],
    }
    defaults.update(kwargs)
    return models.DecimalField(**defaults)
