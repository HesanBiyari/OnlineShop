"""Authentication, password policy and login throttling."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .helpers import PASSWORD, make_user

User = get_user_model()


class SignupTests(TestCase):
    def _signup(self, **overrides):
        data = {
            "phone": "09121234567",
            "email": "new@example.com",
            "password1": "Xk9!mQ2z#Lp7",
            "password2": "Xk9!mQ2z#Lp7",
        }
        data.update(overrides)
        return self.client.post(reverse("signup"), data)

    def test_signup_normalises_phone(self):
        response = self._signup(phone="+98 912 123 4567")
        self.assertEqual(response.status_code, 302)
        user = User.objects.get()
        self.assertEqual(user.username, "09121234567")
        self.assertEqual(user.email, "new@example.com")

    def test_weak_password_is_rejected(self):
        response = self._signup(password1="12345678", password2="12345678")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_mismatched_passwords_are_rejected(self):
        response = self._signup(password2="Different!234")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_duplicate_phone_or_email_is_rejected(self):
        make_user("09121234567", email="used@example.com")
        response = self._signup()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user("09121234567")

    def test_valid_login_redirects_to_account(self):
        response = self.client.post(
            reverse("login"), {"phone": "09121234567", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("account"))

    def test_existing_plain_username_can_login(self):
        staff = make_user("panel-admin", is_staff=True)
        response = self.client.post(
            reverse("login"), {"phone": "panel-admin", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("account"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), staff.pk)

    def test_external_next_is_rejected(self):
        response = self.client.post(
            reverse("login"),
            {
                "phone": "09121234567",
                "password": PASSWORD,
                "next": "https://evil.example/steal",
            },
        )
        self.assertRedirects(response, reverse("account"))

    def test_local_next_is_honoured(self):
        response = self.client.post(
            reverse("login"),
            {"phone": "09121234567", "password": PASSWORD, "next": "/wishlist/"},
        )
        self.assertRedirects(response, "/wishlist/")

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.client.post(
                reverse("login"),
                {"phone": "09121234567", "password": "WrongPass!234"},
            )

        self.client.post(
            reverse("login"), {"phone": "09121234567", "password": PASSWORD}
        )
        self.assertNotIn("_auth_user_id", self.client.session)

        cache.clear()
        response = self.client.post(
            reverse("login"), {"phone": "09121234567", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("account"))

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 302)
