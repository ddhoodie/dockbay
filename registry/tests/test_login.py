from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from registry.models import User
from registry.roles import account_role


class AccountRoleTests(TestCase):
    def test_anonymous_ordinary_user_and_administrator_are_distinct(self):
        ordinary = User(username="milan")
        administrator = User(username="ana", is_staff=True)

        self.assertEqual(account_role(AnonymousUser()), "neautentifikovan")
        self.assertEqual(account_role(ordinary), "običan korisnik")
        self.assertEqual(account_role(administrator), "administrator")
        self.assertNotEqual(account_role(ordinary), account_role(administrator))


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="milan", password="milan-pass-1")

    def test_registered_user_logs_in_and_the_session_knows_them(self):
        response = self.client.post(
            "/login/",
            {"username": "milan", "password": "milan-pass-1"},
        )

        self.assertRedirects(response, "/")
        home = self.client.get("/")
        self.assertContains(home, "milan")
        self.assertContains(home, "običan korisnik")
        self.assertNotContains(home, "Novi administrator")

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            "/login/",
            {"username": "milan", "password": "not-the-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_ends_the_session(self):
        self.client.post(
            "/login/",
            {"username": "milan", "password": "milan-pass-1"},
        )

        self.client.post("/logout/")
        home = self.client.get("/")

        self.assertContains(home, "Prijavi se")
        self.assertNotContains(home, "Prijavljen si kao milan")

    def test_administrator_is_not_offered_superadmin_actions(self):
        User.objects.create_user(
            username="ana",
            password="ana-admin-pass-1",
            is_staff=True,
        )
        self.client.post(
            "/login/",
            {"username": "ana", "password": "ana-admin-pass-1"},
        )

        home = self.client.get("/")
        self.assertContains(home, "administrator")
        self.assertNotContains(home, "Novi administrator")
