from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from registry.forms import TagPushForm
from registry.models import Repository, Tag, User


class TagTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.repository = Repository.objects.create(
            owner=self.owner,
            name="api",
            description="An API image.",
            visibility=Repository.Visibility.PUBLIC,
        )

    def test_a_tag_records_its_author_and_creation_time(self):
        tag = Tag.objects.create(repository=self.repository, name="1.0", author="Milan")

        self.assertEqual(str(tag), "milan/api:1.0")
        self.assertEqual(tag.author, "Milan")
        self.assertIsNotNone(tag.created_at)

    def test_a_repository_cannot_have_two_tags_with_the_same_name(self):
        Tag.objects.create(repository=self.repository, name="latest", author="Milan")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Tag.objects.create(repository=self.repository, name="latest", author="Ana")

    def test_another_repository_can_use_the_same_tag_name(self):
        other = Repository.objects.create(
            owner=self.owner,
            name="web",
            description="A web image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        Tag.objects.create(repository=self.repository, name="latest", author="Milan")
        Tag.objects.create(repository=other, name="latest", author="Milan")

        self.assertEqual(Tag.objects.filter(name="latest").count(), 2)

    def test_deleting_a_repository_deletes_its_tags(self):
        Tag.objects.create(repository=self.repository, name="latest", author="Milan")

        self.repository.delete()

        self.assertFalse(Tag.objects.exists())

    def test_push_form_rejects_a_bad_tag_a_duplicate_and_the_wrong_image(self):
        Tag.objects.create(repository=self.repository, name="latest", author="Milan")

        invalid_name = TagPushForm(
            self.repository,
            data={"image_name": "milan/api", "author": "Milan", "tag": "-bad"},
        )
        duplicate = TagPushForm(
            self.repository,
            data={"image_name": "milan/api", "author": "Milan", "tag": "latest"},
        )
        wrong_image = TagPushForm(
            self.repository,
            data={"image_name": "milan/web", "author": "Milan", "tag": "1.0"},
        )
        blank_author = TagPushForm(
            self.repository,
            data={"image_name": "milan/api", "author": "   ", "tag": "1.0"},
        )

        self.assertFalse(invalid_name.is_valid())
        self.assertIn("tag", invalid_name.errors)
        self.assertFalse(duplicate.is_valid())
        self.assertIn("tag", duplicate.errors)
        self.assertFalse(wrong_image.is_valid())
        self.assertIn("image_name", wrong_image.errors)
        self.assertFalse(blank_author.is_valid())
        self.assertIn("author", blank_author.errors)

    def test_push_form_stores_a_tag_on_the_repository(self):
        form = TagPushForm(
            self.repository,
            data={"image_name": " milan/api ", "author": " Milan ", "tag": "1.0"},
        )

        self.assertTrue(form.is_valid(), form.errors)
        tag = form.save()

        self.assertEqual(tag.repository, self.repository)
        self.assertEqual(tag.name, "1.0")
        self.assertEqual(tag.author, "Milan")


class TagPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.other = User.objects.create_user(username="ana", password="ana-admin-pass-1")
        self.repository = Repository.objects.create(
            owner=self.owner,
            name="api",
            description="An API image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        self.client.login(username="milan", password="milan-pass-1")

    def test_owner_adds_lists_filters_and_deletes_a_tag(self):
        created = self.client.post(
            "/repositories/milan/api/tags/new/",
            {"image_name": "milan/api", "author": "Milan", "tag": "1.0"},
        )
        self.assertRedirects(created, "/repositories/milan/api/")

        listed = self.client.get("/repositories/milan/api/")
        self.assertContains(listed, "milan/api:1.0")
        self.assertContains(listed, "Milan")

        Tag.objects.create(repository=self.repository, name="latest", author="Milan")
        filtered = self.client.get("/repositories/milan/api/", {"name": "LAT"})
        self.assertContains(filtered, "milan/api:latest")
        self.assertNotContains(filtered, "milan/api:1.0")

        response = self.client.post("/repositories/milan/api/tags/1.0/delete/")
        self.assertRedirects(response, "/repositories/milan/api/")
        self.assertFalse(Tag.objects.filter(repository=self.repository, name="1.0").exists())
        self.assertTrue(Tag.objects.filter(repository=self.repository, name="latest").exists())

    def test_tags_sort_by_name_and_by_newest(self):
        earlier = Tag.objects.create(repository=self.repository, name="alpha", author="Milan")
        newest = Tag.objects.create(repository=self.repository, name="zeta", author="Milan")
        Tag.objects.filter(pk=earlier.pk).update(created_at=timezone.now() - timedelta(days=2))
        Tag.objects.filter(pk=newest.pk).update(created_at=timezone.now())

        by_name = self.client.get("/repositories/milan/api/").content.decode()
        self.assertLess(by_name.index("milan/api:alpha"), by_name.index("milan/api:zeta"))

        by_newest = self.client.get("/repositories/milan/api/", {"sort": "created"}).content.decode()
        self.assertLess(by_newest.index("milan/api:zeta"), by_newest.index("milan/api:alpha"))

    def test_another_user_can_see_public_tags_but_cannot_change_them(self):
        Tag.objects.create(repository=self.repository, name="latest", author="Milan")
        self.client.login(username="ana", password="ana-admin-pass-1")

        detail = self.client.get("/repositories/milan/api/")
        self.assertContains(detail, "milan/api:latest")
        self.assertNotContains(detail, "New push")
        self.assertEqual(self.client.get("/repositories/milan/api/tags/new/").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/repositories/milan/api/tags/new/",
                {"image_name": "milan/api", "author": "Ana", "tag": "1.0"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/repositories/milan/api/tags/latest/delete/").status_code,
            403,
        )
        self.assertTrue(Tag.objects.filter(repository=self.repository, name="latest").exists())

    def test_a_private_repository_hides_its_tags_from_another_user(self):
        self.repository.visibility = Repository.Visibility.PRIVATE
        self.repository.save()
        Tag.objects.create(repository=self.repository, name="latest", author="Milan")
        self.client.login(username="ana", password="ana-admin-pass-1")

        self.assertEqual(self.client.get("/repositories/milan/api/").status_code, 404)
        self.assertEqual(self.client.get("/repositories/milan/api/tags/new/").status_code, 404)
        self.assertEqual(
            self.client.post("/repositories/milan/api/tags/latest/delete/").status_code,
            404,
        )
