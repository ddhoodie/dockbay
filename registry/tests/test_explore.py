from django.test import TestCase

from registry.models import Repository, Tag, User
from registry.search import search_public_repositories


class PublicSearchTests(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user(username="ana", password="ana-admin-pass-1")
        self.milan = User.objects.create_user(username="milan", password="milan-pass-1")
        self.luka = User.objects.create_user(username="luka", password="luka-pass-word-1")
        Repository.objects.create(
            owner=self.ana,
            name="api",
            description="Ana's exact image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        Repository.objects.create(
            owner=self.milan,
            name="api-gateway",
            description="A gateway.",
            visibility=Repository.Visibility.PUBLIC,
        )
        Repository.objects.create(
            owner=self.luka,
            name="web",
            description="Runs an api.",
            visibility=Repository.Visibility.PUBLIC,
        )
        Repository.objects.create(
            owner=self.milan,
            name="api",
            description="Hidden private api.",
            visibility=Repository.Visibility.PRIVATE,
        )

    def test_relevance_ranks_exact_name_then_partial_name_then_description(self):
        names = [repository.full_name for repository in search_public_repositories("API")]

        self.assertEqual(names, ["ana/api", "milan/api-gateway", "luka/web"])

    def test_an_empty_query_lists_public_repositories_by_name(self):
        names = [repository.full_name for repository in search_public_repositories("  ")]

        self.assertEqual(names, ["ana/api", "luka/web", "milan/api-gateway"])

    def test_a_match_only_in_the_owner_name_ranks_with_description_matches(self):
        owner = User.objects.create_user(username="apibot", password="apibot-pass-1")
        Repository.objects.create(
            owner=owner,
            name="notes",
            description="Plain notes.",
            visibility=Repository.Visibility.PUBLIC,
        )

        names = [repository.full_name for repository in search_public_repositories("api")]

        self.assertLess(names.index("milan/api-gateway"), names.index("apibot/notes"))
        self.assertLess(names.index("apibot/notes"), names.index("luka/web"))

    def test_a_private_repository_is_absent(self):
        names = [repository.full_name for repository in search_public_repositories("api")]

        self.assertNotIn("milan/api", names)

    def test_the_same_score_is_ordered_by_full_name(self):
        bob = User.objects.create_user(username="bob", password="bob-pass-word-1")
        Repository.objects.create(
            owner=bob,
            name="api",
            description="Bob's exact image.",
            visibility=Repository.Visibility.PUBLIC,
        )

        names = [repository.full_name for repository in search_public_repositories("api")]

        self.assertLess(names.index("ana/api"), names.index("bob/api"))

    def test_badge_filter_keeps_only_public_repositories_with_that_badge(self):
        Repository.objects.create(
            name="python",
            description="The Python image.",
            visibility=Repository.Visibility.PUBLIC,
            official=True,
        )
        self.milan.verified_publisher = True
        self.milan.save()
        self.luka.sponsored_oss = True
        self.luka.save()
        Repository.objects.create(
            name="secret",
            description="Official but private.",
            visibility=Repository.Visibility.PRIVATE,
            official=True,
        )

        official = [repository.full_name for repository in search_public_repositories("", "official")]
        verified = [repository.full_name for repository in search_public_repositories("", "verified")]
        sponsored = [repository.full_name for repository in search_public_repositories("", "sponsored")]

        self.assertEqual(official, ["python"])
        self.assertEqual(verified, ["milan/api-gateway"])
        self.assertEqual(sponsored, ["luka/web"])


class ExplorePageTests(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user(username="ana", password="ana-admin-pass-1")
        self.milan = User.objects.create_user(username="milan", password="milan-pass-1")
        self.public = Repository.objects.create(
            owner=self.ana,
            name="api",
            description="An exact image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        self.official = Repository.objects.create(
            name="python",
            description="The Python image.",
            visibility=Repository.Visibility.PUBLIC,
            official=True,
        )
        Repository.objects.create(
            owner=self.milan,
            name="api",
            description="Hidden private api.",
            visibility=Repository.Visibility.PRIVATE,
        )
        Tag.objects.create(repository=self.public, name="latest", author="Ana")

    def test_anonymous_visitor_searches_sorts_and_opens_a_public_repository(self):
        listed = self.client.get("/explore/", {"q": "api"})
        self.assertContains(listed, "ana/api")
        self.assertNotContains(listed, "milan/api")
        self.assertNotContains(listed, "Hidden private api.")

        detail = self.client.get("/repositories/ana/api/")
        self.assertContains(detail, "An exact image.")
        self.assertContains(detail, "ana/api:latest")
        self.assertContains(detail, "Stars: 0")
        self.assertNotContains(detail, "New push")
        self.assertEqual(self.client.get("/repositories/milan/api/").status_code, 404)

        official = self.client.get("/explore/", {"q": "python"})
        self.assertContains(official, "python")
        self.assertContains(official, "Docker Official Image")
        self.assertContains(official, 'href="/official/python/"')
        official_detail = self.client.get("/official/python/")
        self.assertContains(official_detail, "Docker Official Image")
        self.assertNotContains(official_detail, "New push")

    def test_badge_filter_hides_a_public_repository_without_that_badge(self):
        Repository.objects.create(
            owner=self.ana,
            name="web",
            description="No badge.",
            visibility=Repository.Visibility.PUBLIC,
        )

        response = self.client.get("/explore/", {"badge": "official"})

        self.assertContains(response, "python")
        self.assertNotContains(response, "ana/web")
        self.assertNotContains(response, "ana/api")
