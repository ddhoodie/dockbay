import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from registry.bootstrap import SUPERADMIN_USERNAME, create_initial_superadmin


def _credentials(path):
    data = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        key, value = line.split("=", 1)
        data[key] = value
    return data


class SuperadminBootstrapTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "superadmin_password.txt")
        self.override = override_settings(SUPERADMIN_PASSWORD_FILE=self.path)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.directory.cleanup()

    def test_creates_one_superadmin_and_writes_the_password(self):
        user = create_initial_superadmin()
        written = _credentials(self.path)

        self.assertEqual(user.username, SUPERADMIN_USERNAME)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.check_password(written["password"]))
        self.assertEqual(written["username"], SUPERADMIN_USERNAME)

    def test_second_call_keeps_the_same_account_and_password_file(self):
        create_initial_superadmin()
        first_write = Path(self.path).read_text(encoding="utf-8")

        create_initial_superadmin()

        User = get_user_model()
        self.assertEqual(User.objects.filter(is_superuser=True).count(), 1)
        self.assertEqual(Path(self.path).read_text(encoding="utf-8"), first_write)


class SuperadminAccessTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "superadmin_password.txt")
        self.override = override_settings(SUPERADMIN_PASSWORD_FILE=self.path)
        self.override.enable()
        create_initial_superadmin()
        self.password = _credentials(self.path)["password"]

    def tearDown(self):
        self.override.disable()
        self.directory.cleanup()

    def test_login_stops_at_the_password_change(self):
        response = self.client.post(
            "/login/",
            {"username": SUPERADMIN_USERNAME, "password": self.password},
        )

        self.assertRedirects(response, "/password/change/")
        blocked = self.client.get("/administrators/new/")
        self.assertRedirects(blocked, "/password/change/")

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            "/login/",
            {"username": SUPERADMIN_USERNAME, "password": "not-the-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_short_password_does_not_open_the_app(self):
        self.client.post(
            "/login/",
            {"username": SUPERADMIN_USERNAME, "password": self.password},
        )
        response = self.client.post(
            "/password/change/",
            {
                "old_password": self.password,
                "new_password1": "123",
                "new_password2": "123",
            },
        )

        self.assertEqual(response.status_code, 200)
        user = get_user_model().objects.get(username=SUPERADMIN_USERNAME)
        self.assertTrue(user.must_change_password)

    def test_superadmin_can_add_an_administrator_after_the_change(self):
        self.client.post(
            "/login/",
            {"username": SUPERADMIN_USERNAME, "password": self.password},
        )
        changed = self.client.post(
            "/password/change/",
            {
                "old_password": self.password,
                "new_password1": "new-super-pass-1",
                "new_password2": "new-super-pass-1",
            },
        )
        self.assertRedirects(changed, "/")

        created = self.client.post(
            "/administrators/new/",
            {"username": "ana", "password": "ana-admin-pass-1"},
        )
        self.assertEqual(created.status_code, 200)
        admin = get_user_model().objects.get(username="ana")
        self.assertTrue(admin.is_staff)
        self.assertFalse(admin.is_superuser)

        self.client.post("/logout/")
        self.client.post(
            "/login/",
            {"username": "ana", "password": "ana-admin-pass-1"},
        )
        forbidden = self.client.get("/administrators/new/")
        self.assertEqual(forbidden.status_code, 403)

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get("/administrators/new/")
        self.assertRedirects(response, "/login/?next=/administrators/new/")
