from django.test import TestCase

from registry.forms import OfficialRepositoryCreateForm, RepositoryCreateForm
from registry.models import Repository, Tag, User


class OfficialRepositoryModelTests(TestCase):
    def test_full_name_is_only_the_repository_name(self):
        repository = Repository.objects.create(
            name="python",
            description="The Python image.",
            visibility=Repository.Visibility.PUBLIC,
            official=True,
        )

        self.assertEqual(repository.full_name, "python")
        self.assertIsNone(repository.owner)
        self.assertIsNone(repository.organization)
        self.assertEqual(repository.badges, ["Docker Official Image"])
        self.assertEqual(repository.get_absolute_url(), "/official/python/")

    def test_an_ordinary_create_form_cannot_make_a_repository_official(self):
        owner = User.objects.create_user(username="milan", password="milan-pass-1")
        form = RepositoryCreateForm(
            owner,
            data={
                "name": "python",
                "description": "Not official.",
                "visibility": Repository.Visibility.PUBLIC,
                "official": True,
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        repository = form.save()
        self.assertFalse(repository.official)
        self.assertEqual(repository.full_name, "milan/python")


class OfficialRepositoryPageTests(TestCase):
    def setUp(self):
        self.administrator = User.objects.create_user(
            username="ana",
            password="ana-admin-pass-1",
            is_staff=True,
        )
        self.ordinary = User.objects.create_user(username="milan", password="milan-pass-1")
        self.client.login(username="ana", password="ana-admin-pass-1")

    def test_administrator_creates_lists_and_manages_an_official_repository(self):
        created = self.client.post(
            "/official/new/",
            {
                "name": "python",
                "description": "The Python image.",
                "visibility": "public",
            },
        )
        self.assertRedirects(created, "/official/python/")

        repository = Repository.objects.get(name="python")
        self.assertTrue(repository.official)
        self.assertEqual(repository.full_name, "python")
        self.assertIsNone(repository.owner_id)

        listed = self.client.get("/repositories/")
        self.assertContains(listed, "New official repository")
        self.assertContains(listed, ">python<")
        self.assertNotContains(listed, "ana/python")

        detail = self.client.get("/official/python/")
        self.assertContains(detail, "The Python image.")
        self.assertContains(detail, "Docker Official Image")
        self.assertContains(detail, "New push")
        self.assertContains(detail, ">Settings<")

        pushed = self.client.post(
            "/official/python/tags/new/",
            {"image_name": "python", "author": "Ana", "tag": "3.12"},
        )
        self.assertRedirects(pushed, "/official/python/")
        self.assertContains(self.client.get("/official/python/"), "python:3.12")

        changed = self.client.post(
            "/official/python/settings/",
            {"description": "Updated official image.", "visibility": "private"},
        )
        self.assertRedirects(changed, "/official/python/")
        repository.refresh_from_db()
        self.assertEqual(repository.description, "Updated official image.")
        self.assertEqual(repository.visibility, Repository.Visibility.PRIVATE)

        deleted_tag = self.client.post("/official/python/tags/3.12/delete/")
        self.assertRedirects(deleted_tag, "/official/python/")
        self.assertFalse(Tag.objects.exists())

        deleted = self.client.post("/official/python/delete/")
        self.assertRedirects(deleted, "/repositories/")
        self.assertFalse(Repository.objects.filter(name="python").exists())

    def test_ordinary_user_cannot_create_or_manage_an_official_repository(self):
        self.client.login(username="milan", password="milan-pass-1")
        Repository.objects.create(
            name="python",
            description="The Python image.",
            visibility=Repository.Visibility.PUBLIC,
            official=True,
        )

        listed = self.client.get("/repositories/")
        self.assertNotContains(listed, "New official repository")
        self.assertNotContains(listed, ">python<")

        self.assertEqual(self.client.get("/official/new/").status_code, 403)
        created = self.client.post(
            "/official/new/",
            {
                "name": "node",
                "description": "Not allowed.",
                "visibility": "public",
            },
        )
        self.assertEqual(created.status_code, 403)
        self.assertFalse(Repository.objects.filter(name="node").exists())

        public = self.client.get("/official/python/")
        self.assertContains(public, "Docker Official Image")
        self.assertNotContains(public, "New push")
        self.assertEqual(self.client.get("/official/python/tags/new/").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/official/python/settings/",
                {"description": "Taken.", "visibility": "private"},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.post("/official/python/delete/").status_code, 403)
        self.assertTrue(Repository.objects.filter(official=True, name="python").exists())

    def test_form_rejects_a_duplicate_official_name(self):
        Repository.objects.create(
            name="python",
            description="The Python image.",
            visibility=Repository.Visibility.PUBLIC,
            official=True,
        )
        form = OfficialRepositoryCreateForm(
            data={
                "name": "python",
                "description": "Another one.",
                "visibility": Repository.Visibility.PUBLIC,
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
