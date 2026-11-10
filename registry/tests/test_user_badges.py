from django.test import TestCase

from registry.forms import BadgeAssignmentForm
from registry.models import Repository, User
from registry.search import search_ordinary_users


class OrdinaryUserSearchTests(TestCase):
    def test_search_matches_usernames_case_insensitively_and_excludes_administrators(self):
        ordinary = User.objects.create_user(username="ordinary-search", password="user-pass-1")
        User.objects.create_user(username="staff-search", password="staff-pass-1", is_staff=True)
        User.objects.create_superuser(username="super-search", password="super-pass-1")

        users = list(search_ordinary_users("SEARCH"))

        self.assertEqual(users, [ordinary])


class BadgeAssignmentFormTests(TestCase):
    def test_assignment_sets_each_badge_and_can_be_repeated(self):
        user = User.objects.create_user(username="milan", password="milan-pass-1")

        for badge in ("verified_publisher", "sponsored_oss", "verified_publisher"):
            form = BadgeAssignmentForm(data={"user": user.pk, "badge": badge})
            self.assertTrue(form.is_valid(), form.errors)
            form.save()

        user.refresh_from_db()
        self.assertTrue(user.verified_publisher)
        self.assertTrue(user.sponsored_oss)

    def test_assignment_rejects_administrators_and_superusers(self):
        administrator = User.objects.create_user(
            username="ana",
            password="ana-admin-pass-1",
            is_staff=True,
        )
        superadmin = User.objects.create_superuser(
            username="superadmin",
            password="super-pass-1",
        )

        for user in (administrator, superadmin):
            form = BadgeAssignmentForm(
                data={"user": user.pk, "badge": "verified_publisher"},
            )
            self.assertFalse(form.is_valid())
            self.assertIn("user", form.errors)


class UserBadgePageTests(TestCase):
    def setUp(self):
        self.administrator = User.objects.create_user(
            username="ana",
            password="ana-admin-pass-1",
            is_staff=True,
        )
        self.user = User.objects.create_user(username="milan", password="milan-pass-1")
        self.superadmin = User.objects.create_superuser(
            username="superadmin",
            password="super-pass-1",
        )
        self.public = Repository.objects.create(
            owner=self.user,
            name="api",
            description="A public image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        self.private = Repository.objects.create(
            owner=self.user,
            name="secret",
            description="A private image.",
            visibility=Repository.Visibility.PRIVATE,
        )

    def test_administrator_searches_only_ordinary_users(self):
        self.client.login(username="ana", password="ana-admin-pass-1")

        response = self.client.get("/administrators/users/", {"q": "a"})

        self.assertContains(response, "milan")
        self.assertNotContains(response, "ana-admin-pass-1")
        self.assertNotContains(response, ">ana<")
        self.assertNotContains(response, "superadmin")

    def test_administrator_assigns_both_badges_through_post(self):
        self.client.login(username="ana", password="ana-admin-pass-1")

        for badge in ("verified_publisher", "sponsored_oss"):
            response = self.client.post(
                "/administrators/users/",
                {"user": self.user.pk, "badge": badge},
            )
            self.assertContains(response, "Badge assigned.")

        self.user.refresh_from_db()
        self.assertTrue(self.user.verified_publisher)
        self.assertTrue(self.user.sponsored_oss)

    def test_assignment_appears_on_explore_and_public_repository_detail(self):
        self.client.login(username="ana", password="ana-admin-pass-1")
        self.client.post(
            "/administrators/users/",
            {"user": self.user.pk, "badge": "verified_publisher"},
        )

        explore = self.client.get("/explore/", {"badge": "verified"})
        self.assertContains(explore, "milan/api")
        self.assertContains(explore, "Verified Publisher")
        self.assertNotContains(explore, "milan/secret")

        detail = self.client.get("/repositories/milan/api/")
        self.assertContains(detail, "Verified Publisher")
        self.assertEqual(self.client.get("/repositories/milan/secret/").status_code, 404)

    def test_ordinary_user_cannot_access_or_submit_assignment(self):
        self.client.login(username="milan", password="milan-pass-1")

        self.assertEqual(self.client.get("/administrators/users/").status_code, 403)
        response = self.client.post(
            "/administrators/users/",
            {"user": self.user.pk, "badge": "verified_publisher"},
        )

        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertFalse(self.user.verified_publisher)

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get("/administrators/users/")

        self.assertRedirects(response, "/login/?next=/administrators/users/")

    def test_crafted_post_cannot_assign_a_badge_to_an_administrator_or_superuser(self):
        self.client.login(username="ana", password="ana-admin-pass-1")

        for user in (self.administrator, self.superadmin):
            response = self.client.post(
                "/administrators/users/",
                {"user": user.pk, "badge": "verified_publisher"},
            )
            self.assertEqual(response.status_code, 200)
            user.refresh_from_db()
            self.assertFalse(user.verified_publisher)
