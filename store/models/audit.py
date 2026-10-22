"""Append-only audit trail for sensitive staff actions."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    ACTION_DIGITAL_EXPORT = "digital_codes.export"
    ACTION_DIGITAL_IMPORT = "digital_codes.import"
    ACTION_ORDER_STATUS = "order.status_changed"
    ACTION_STAFF_EDIT = "staff.object_changed"
    ACTION_LOGIN_LOCKOUT = "auth.lockout"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("action", "-created_at")),
            models.Index(fields=("actor", "-created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M}"
