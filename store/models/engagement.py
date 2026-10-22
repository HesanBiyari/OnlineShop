"""Customer engagement: wishlists, reviews, recent views and notifications."""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Wishlist(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    product = models.ForeignKey(
        "store.Product", on_delete=models.CASCADE, related_name="wishlists"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "product"), name="unique_wishlist_user_product"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id} - {self.product_id}"


class Review(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    product = models.ForeignKey(
        "store.Product", on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=120, blank=True)
    body = models.TextField(max_length=2000)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "product"), name="unique_review_user_product"
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=1) & Q(rating__lte=5),
                name="review_rating_1_5",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} - {self.rating}/5"


class RecentlyViewed(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="recently_viewed",
    )
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    product = models.ForeignKey(
        "store.Product", on_delete=models.CASCADE, related_name="recent_views"
    )
    viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-viewed_at",)

    def __str__(self) -> str:
        return f"{self.product_id}"


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title
