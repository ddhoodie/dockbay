from django.test import TestCase

from registry.models import Organization, Repository, User


def create_repository(owner, name="api", visibility=Repository.Visibility.PUBLIC):
    return Repository.objects.create(
        owner=owner,
        name=name,
        description=f"The {name} image.",
        visibility=visibility,
    )


class RepositoryStarModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="owner-pass-1")
        self.first = User.objects.create_user(username="first", password="first-pass-1")
        self.second = User.objects.create_user(username="second", password="second-pass-1")
        self.repository = create_repository(self.owner)

    def test_counts_distinct_users_and_exposes_the_reverse_relationship(self):
        self.assertEqual(self.repository.star_count, 0)

        self.repository.starred_by.add(self.first)
        self.assertEqual(self.repository.star_count, 1)
        self.assertEqual(list(self.first.starred_repositories.all()), [self.repository])

        self.repository.starred_by.add(self.first)
        self.assertEqual(self.repository.star_count, 1)

        self.repository.starred_by.add(self.second)
        self.assertEqual(self.repository.star_count, 2)

    def test_deleting_a_user_cleans_up_the_star(self):
        self.repository.starred_by.add(self.first)

        self.first.delete()

        self.assertEqual(self.repository.star_count, 0)

    def test_deleting_a_repository_cleans_up_the_reverse_relationship(self):
        self.repository.starred_by.add(self.first)

        self.repository.delete()

        self.assertFalse(self.first.starred_repositories.exists())


class RepositoryStarIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="owner-pass-1")
        self.user = User.objects.create_user(username="user", password="user-pass-1")
        self.member = User.objects.create_user(username="member", password="member-pass-1")
        self.staff = User.objects.create_user(
            username="staff", password="staff-pass-1", is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            username="root", password="root-pass-1"
        )
        self.personal = create_repository(self.owner)
        self.private = create_repository(
            self.owner, "secret", Repository.Visibility.PRIVATE
        )
        self.organization = Organization.objects.create(
            owner=self.owner,
            name="dockbay",
            description="Dockbay organization.",
            image="organizations/dockbay.png",
        )
        self.organization.members.add(self.member)
        self.organization_repository = Repository.objects.create(
            organization=self.organization,
            name="worker",
            description="The worker image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        self.official = Repository.objects.create(
            name="python",
            description="The Python image.",
            visibility=Repository.Visibility.PUBLIC,
            official=True,
        )

    def star_path(self, repository):
        return f"/repositories/{repository.pk}/star/"

    def test_ordinary_user_stars_a_public_personal_repository_idempotently(self):
        self.client.login(username="user", password="user-pass-1")

        before = self.client.get(self.personal.get_absolute_url())
        self.assertContains(before, "Stars: 0")
        self.assertContains(before, ">Star<")

        response = self.client.post(self.star_path(self.personal))
        self.assertRedirects(response, self.personal.get_absolute_url())
        self.assertEqual(self.personal.star_count, 1)

        after = self.client.get(self.personal.get_absolute_url())
        self.assertContains(after, "Stars: 1")
        self.assertContains(after, "Starred")
        self.assertNotContains(after, ">Star<")

        self.client.post(self.star_path(self.personal))
        self.assertEqual(self.personal.star_count, 1)

    def test_outsider_stars_a_public_organization_repository(self):
        self.client.login(username="user", password="user-pass-1")

        response = self.client.post(self.star_path(self.organization_repository))

        self.assertRedirects(response, self.organization_repository.get_absolute_url())
        self.assertEqual(self.organization_repository.star_count, 1)

    def test_ordinary_user_stars_a_public_official_repository(self):
        self.client.login(username="user", password="user-pass-1")

        response = self.client.post(self.star_path(self.official))

        self.assertRedirects(response, self.official.get_absolute_url())
        self.assertEqual(self.official.star_count, 1)

    def test_owner_and_organization_member_cannot_star(self):
        for username, password, repository in (
            ("owner", "owner-pass-1", self.personal),
            ("member", "member-pass-1", self.organization_repository),
        ):
            with self.subTest(username=username):
                self.client.login(username=username, password=password)
                response = self.client.post(self.star_path(repository))
                self.assertEqual(response.status_code, 403)
                self.assertEqual(repository.star_count, 0)
                detail = self.client.get(repository.get_absolute_url())
                self.assertNotContains(detail, ">Star<")

    def test_private_repository_cannot_be_starred(self):
        self.client.login(username="user", password="user-pass-1")

        response = self.client.post(self.star_path(self.private))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.private.star_count, 0)

    def test_administrator_and_superuser_cannot_star(self):
        for username, password in (
            ("staff", "staff-pass-1"),
            ("root", "root-pass-1"),
        ):
            with self.subTest(username=username):
                self.client.login(username=username, password=password)
                response = self.client.post(self.star_path(self.personal))
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.personal.star_count, 0)
                self.assertNotContains(
                    self.client.get(self.personal.get_absolute_url()), ">Star<"
                )

    def test_anonymous_post_redirects_to_login(self):
        path = self.star_path(self.personal)

        response = self.client.post(path)

        self.assertRedirects(response, f"/login/?next={path}")
        self.assertEqual(self.personal.star_count, 0)

    def test_get_and_malformed_requests_do_not_create_a_star(self):
        self.client.login(username="user", password="user-pass-1")

        self.assertEqual(self.client.get(self.star_path(self.personal)).status_code, 405)
        self.assertEqual(self.client.post("/repositories/not-an-id/star/").status_code, 404)
        self.assertEqual(self.personal.star_count, 0)

    def test_star_form_is_hidden_from_anonymous_users(self):
        response = self.client.get(self.personal.get_absolute_url())

        self.assertNotContains(response, ">Star<")


class StarredRepositoryProfileTests(TestCase):
    def setUp(self):
        self.subject = User.objects.create_user(
            username="subject", password="subject-pass-1"
        )
        self.viewer = User.objects.create_user(username="viewer", password="viewer-pass-1")
        owner = User.objects.create_user(username="owner", password="owner-pass-1")
        self.personal = create_repository(owner, "personal")
        organization = Organization.objects.create(
            owner=owner,
            name="dockbay",
            description="Dockbay organization.",
            image="organizations/dockbay.png",
        )
        self.organization_repository = Repository.objects.create(
            organization=organization,
            name="organization",
            description="An organization image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        self.official = Repository.objects.create(
            name="official",
            description="An official image.",
            visibility=Repository.Visibility.PUBLIC,
            official=True,
        )
        self.unrelated = create_repository(owner, "unrelated")
        self.private = create_repository(owner, "private", Repository.Visibility.PRIVATE)
        self.subject.starred_repositories.add(
            self.personal, self.organization_repository, self.official, self.private
        )

    def test_own_and_other_profiles_list_all_starred_repository_types(self):
        for username, password in (
            ("subject", "subject-pass-1"),
            ("viewer", "viewer-pass-1"),
        ):
            with self.subTest(username=username):
                self.client.login(username=username, password=password)
                response = self.client.get("/users/subject/")
                for repository in (
                    self.personal,
                    self.organization_repository,
                    self.official,
                ):
                    self.assertContains(response, repository.full_name)
                    self.assertContains(
                        response, f'href="{repository.get_absolute_url()}"'
                    )
                self.assertNotContains(response, self.unrelated.full_name)
                self.assertNotContains(response, self.private.full_name)

    def test_profile_without_stars_displays_the_empty_state(self):
        self.client.login(username="subject", password="subject-pass-1")

        response = self.client.get("/users/viewer/")

        self.assertContains(response, "No starred repositories.")
