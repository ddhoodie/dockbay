from django.test import TestCase

from registry.forms import RegisterForm
from registry.models import User


def _registration(username="milan", password="milan-pass-1", confirmation=None):
    return {
        "username": username,
        "password": password,
        "password_confirmation": password if confirmation is None else confirmation,
    }


class RegisterFormTests(TestCase):
    def test_accepts_a_new_username(self):
        form = RegisterForm(data=_registration())
        self.assertTrue(form.is_valid())

    def test_rejects_a_taken_username(self):
        User.objects.create_user(username="milan", password="milan-pass-1")
        form = RegisterForm(data=_registration())
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_rejects_a_short_password(self):
        form = RegisterForm(data=_registration(password="123"))
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_rejects_a_mismatched_confirmation(self):
        form = RegisterForm(data=_registration(confirmation="other-pass-1"))
        self.assertFalse(form.is_valid())
        self.assertIn("password_confirmation", form.errors)


class RegistrationTests(TestCase):
    def test_anonymous_visitor_becomes_an_ordinary_user(self):
        response = self.client.post("/register/", _registration())

        self.assertRedirects(response, "/login/")
        user = User.objects.get(username="milan")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.must_change_password)
        self.assertTrue(user.check_password("milan-pass-1"))

    def test_duplicate_username_does_not_create_another_account(self):
        User.objects.create_user(username="milan", password="milan-pass-1")

        response = self.client.post("/register/", _registration())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="milan").count(), 1)
        self.assertContains(response, "Korisničko ime je zauzeto.")

    def test_signed_in_user_is_sent_home(self):
        User.objects.create_user(username="milan", password="milan-pass-1")
        self.client.login(username="milan", password="milan-pass-1")

        response = self.client.get("/register/")

        self.assertRedirects(response, "/")
