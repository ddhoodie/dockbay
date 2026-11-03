from django.test import TestCase

from registry.forms import ProfileForm
from registry.models import User


class ProfileFormTests(TestCase):
    def test_edits_display_name_email_and_bio_only(self):
        user = User.objects.create_user(username="milan", password="milan-pass-1")
        form = ProfileForm(
            data={
                "display_name": "Milan M",
                "email": "milan@example.com",
                "bio": "Builds images.",
            },
            instance=user,
        )

        self.assertTrue(form.is_valid())
        self.assertNotIn("username", form.fields)
        saved = form.save()
        self.assertEqual(saved.username, "milan")
        self.assertEqual(saved.display_name, "Milan M")
        self.assertEqual(saved.email, "milan@example.com")
        self.assertEqual(saved.bio, "Builds images.")


class ProfileTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="milan",
            password="milan-pass-1",
            email="old@example.com",
        )
        self.other = User.objects.create_user(
            username="ana",
            password="ana-admin-pass-1",
            email="ana@example.com",
        )
        self.client.login(username="milan", password="milan-pass-1")

    def test_owner_sees_the_profile_form(self):
        response = self.client.get("/users/milan/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "old@example.com")
        self.assertContains(response, "Save")

    def test_owner_saves_a_change_and_keeps_the_username(self):
        response = self.client.post(
            "/users/milan/",
            {
                "display_name": "Milan M",
                "email": "milan@example.com",
                "bio": "Builds images.",
            },
        )

        self.assertRedirects(response, "/users/milan/")
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, "milan")
        self.assertEqual(self.owner.display_name, "Milan M")
        self.assertEqual(self.owner.email, "milan@example.com")
        self.assertEqual(self.owner.bio, "Builds images.")

    def test_another_user_cannot_edit_the_profile(self):
        response = self.client.post(
            "/users/ana/",
            {
                "display_name": "Taken",
                "email": "taken@example.com",
                "bio": "Nope.",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.other.refresh_from_db()
        self.assertEqual(self.other.email, "ana@example.com")
        self.assertEqual(self.other.display_name, "")
