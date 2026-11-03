from django.test import TestCase

from registry.forms import RepositoryCreateForm
from registry.models import Repository, User


class RepositoryTests(TestCase):
    def test_full_name_is_username_and_name(self):
        owner = User.objects.create_user(username="milan", password="milan-pass-1")
        repository = Repository.objects.create(
            owner=owner,
            name="api",
            description="An API image.",
            visibility=Repository.Visibility.PUBLIC,
        )

        self.assertEqual(repository.full_name, "milan/api")

    def test_the_same_owner_cannot_reuse_a_name(self):
        owner = User.objects.create_user(username="milan", password="milan-pass-1")
        Repository.objects.create(
            owner=owner,
            name="api",
            description="An API image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        form = RepositoryCreateForm(
            owner,
            data={
                "name": "api",
                "description": "Another one.",
                "visibility": Repository.Visibility.PRIVATE,
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_another_owner_can_use_the_same_name(self):
        milan = User.objects.create_user(username="milan", password="milan-pass-1")
        ana = User.objects.create_user(username="ana", password="ana-admin-pass-1")
        Repository.objects.create(
            owner=milan,
            name="api",
            description="Milan's API.",
            visibility=Repository.Visibility.PUBLIC,
        )
        form = RepositoryCreateForm(
            ana,
            data={
                "name": "api",
                "description": "Ana's API.",
                "visibility": Repository.Visibility.PUBLIC,
            },
        )

        self.assertTrue(form.is_valid())


class RepositoryPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.other = User.objects.create_user(username="ana", password="ana-admin-pass-1")
        self.client.login(username="milan", password="milan-pass-1")

    def test_owner_creates_lists_filters_and_opens_a_repository(self):
        created = self.client.post(
            "/repositories/new/",
            {
                "name": "api",
                "description": "An API image.",
                "visibility": "public",
            },
        )
        self.assertRedirects(created, "/repositories/milan/api/")

        listed = self.client.get("/repositories/")
        self.assertContains(listed, "milan/api")

        filtered = self.client.get("/repositories/", {"name": "api", "visibility": "public"})
        self.assertContains(filtered, "milan/api")
        hidden = self.client.get("/repositories/", {"visibility": "private"})
        self.assertNotContains(hidden, "milan/api")

        detail = self.client.get("/repositories/milan/api/")
        self.assertContains(detail, "An API image.")
        self.assertContains(detail, "public")

    def test_owner_changes_description_and_visibility_but_not_the_name(self):
        Repository.objects.create(
            owner=self.owner,
            name="api",
            description="An API image.",
            visibility=Repository.Visibility.PUBLIC,
        )

        response = self.client.post(
            "/repositories/milan/api/settings/",
            {"description": "Updated image.", "visibility": "private", "name": "renamed"},
        )

        self.assertRedirects(response, "/repositories/milan/api/")
        repository = Repository.objects.get(owner=self.owner)
        self.assertEqual(repository.name, "api")
        self.assertEqual(repository.description, "Updated image.")
        self.assertEqual(repository.visibility, Repository.Visibility.PRIVATE)

    def test_owner_deletes_the_repository(self):
        Repository.objects.create(
            owner=self.owner,
            name="api",
            description="An API image.",
            visibility=Repository.Visibility.PUBLIC,
        )

        response = self.client.post("/repositories/milan/api/delete/")

        self.assertRedirects(response, "/repositories/")
        self.assertFalse(Repository.objects.filter(owner=self.owner, name="api").exists())

    def test_another_user_cannot_change_or_see_a_private_repository(self):
        Repository.objects.create(
            owner=self.owner,
            name="secret",
            description="Hidden.",
            visibility=Repository.Visibility.PRIVATE,
        )
        Repository.objects.create(
            owner=self.owner,
            name="api",
            description="An API image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        self.client.login(username="ana", password="ana-admin-pass-1")

        self.assertEqual(self.client.get("/repositories/milan/secret/").status_code, 404)
        self.assertEqual(self.client.get("/repositories/milan/api/").status_code, 200)
        self.assertEqual(
            self.client.post(
                "/repositories/milan/api/settings/",
                {"description": "Taken.", "visibility": "private"},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.post("/repositories/milan/api/delete/").status_code, 403)
        self.assertTrue(Repository.objects.filter(owner=self.owner, name="api").exists())
