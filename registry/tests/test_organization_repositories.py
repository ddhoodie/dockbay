from django.test import TestCase

from registry.forms import OrganizationRepositoryCreateForm
from registry.models import (
    Organization,
    Repository,
    Tag,
    Team,
    TeamRepositoryPermission,
    User,
)
from registry.search import search_public_repositories


def create_organization(owner, name):
    return Organization.objects.create(
        owner=owner,
        name=name,
        description=f"The {name} organization.",
        image=f"organizations/{name}.png",
    )


def create_repository(organization, name, visibility=Repository.Visibility.PRIVATE):
    return Repository.objects.create(
        organization=organization,
        name=name,
        description=f"The {name} image.",
        visibility=visibility,
    )


def grant(organization, repository, user, access, team_name):
    team = Team.objects.create(
        organization=organization,
        name=team_name,
        description=f"The {team_name} team.",
    )
    team.members.add(user)
    TeamRepositoryPermission.objects.create(
        team=team,
        repository=repository,
        access=access,
    )
    return team


class OrganizationRepositoryModelAndFormTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.other = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.organization = create_organization(self.owner, "dockbay")

    def test_form_creates_only_an_organization_owned_repository(self):
        form = OrganizationRepositoryCreateForm(
            self.organization,
            data={
                "name": "api",
                "description": "An API image.",
                "visibility": Repository.Visibility.PUBLIC,
                "owner": self.other.pk,
                "organization": 999,
            },
        )

        self.assertEqual(list(form.fields), ["name", "description", "visibility"])
        self.assertTrue(form.is_valid(), form.errors)
        repository = form.save()
        self.assertEqual(repository.organization, self.organization)
        self.assertIsNone(repository.owner)
        self.assertEqual(repository.full_name, "dockbay/api")

    def test_duplicate_name_is_scoped_to_the_organization(self):
        create_repository(self.organization, "api")
        other_organization = create_organization(self.other, "harbor")
        duplicate = OrganizationRepositoryCreateForm(
            self.organization,
            data={"name": "api", "description": "Duplicate.", "visibility": "public"},
        )
        other_organization_form = OrganizationRepositoryCreateForm(
            other_organization,
            data={"name": "api", "description": "Allowed.", "visibility": "public"},
        )
        Repository.objects.create(
            owner=self.owner,
            name="api",
            description="Personal image.",
            visibility=Repository.Visibility.PUBLIC,
        )

        self.assertFalse(duplicate.is_valid())
        self.assertIn("already has a repository", duplicate.errors["name"][0])
        self.assertTrue(other_organization_form.is_valid(), other_organization_form.errors)

    def test_deleting_the_organization_cascades_repositories_and_tags(self):
        repository = create_repository(self.organization, "api")
        Tag.objects.create(repository=repository, name="latest", author="Milan")

        self.organization.delete()

        self.assertFalse(Repository.objects.exists())
        self.assertFalse(Tag.objects.exists())


class OrganizationRepositoryCreationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.member = User.objects.create_user(username="ana", password="ana-member-pass-1")
        self.outsider = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.organization = create_organization(self.owner, "dockbay")
        self.organization.members.add(self.member)

    def test_member_creates_a_repository_and_team_ui_can_select_it(self):
        self.client.login(username="ana", password="ana-member-pass-1")
        response = self.client.post(
            "/organizations/dockbay/repositories/new/",
            {"name": "api", "description": "An API image.", "visibility": "private"},
        )

        self.assertRedirects(response, "/organizations/dockbay/repositories/")
        repository = Repository.objects.get(name="api")
        self.assertEqual(repository.organization, self.organization)
        self.assertIsNone(repository.owner)
        self.assertEqual(repository.full_name, "dockbay/api")

        Team.objects.create(
            organization=self.organization,
            name="backend",
            description="API team.",
        )
        self.client.login(username="milan", password="milan-pass-1")
        self.assertContains(
            self.client.get("/organizations/dockbay/teams/backend/"),
            "dockbay/api",
        )

    def test_nonmember_cannot_create_a_repository(self):
        self.client.login(username="luka", password="luka-pass-word-1")

        response = self.client.post(
            "/organizations/dockbay/repositories/new/",
            {"name": "taken", "description": "Not allowed.", "visibility": "public"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Repository.objects.exists())

    def test_duplicate_name_returns_a_friendly_form_error(self):
        create_repository(self.organization, "api")
        self.client.login(username="ana", password="ana-member-pass-1")

        response = self.client.post(
            "/organizations/dockbay/repositories/new/",
            {"name": "api", "description": "Duplicate.", "visibility": "public"},
        )

        self.assertContains(response, "already has a repository")
        self.assertEqual(self.organization.repositories.count(), 1)


class OrganizationRepositoryListTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.member = User.objects.create_user(username="ana", password="ana-member-pass-1")
        self.outsider = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.organization = create_organization(self.owner, "dockbay")
        self.organization.members.add(self.member)
        self.public = create_repository(self.organization, "alpha", Repository.Visibility.PUBLIC)
        self.readable = create_repository(self.organization, "secret")
        self.hidden = create_repository(self.organization, "vault")
        grant(
            self.organization,
            self.readable,
            self.member,
            TeamRepositoryPermission.AccessLevel.READ,
            "readers",
        )
        other_organization = create_organization(self.outsider, "harbor")
        self.other = create_repository(other_organization, "other", Repository.Visibility.PUBLIC)

    def test_member_lists_searches_and_filters_only_visible_repositories(self):
        self.client.login(username="ana", password="ana-member-pass-1")

        listed = self.client.get("/organizations/dockbay/repositories/")
        content = listed.content.decode()
        self.assertContains(listed, "dockbay/alpha")
        self.assertContains(listed, "dockbay/secret")
        self.assertNotContains(listed, "dockbay/vault")
        self.assertNotContains(listed, "harbor/other")
        self.assertLess(content.index("dockbay/alpha"), content.index("dockbay/secret"))
        self.assertContains(listed, "New repository")

        searched = self.client.get("/organizations/dockbay/repositories/", {"name": "SEC"})
        self.assertContains(searched, "dockbay/secret")
        self.assertNotContains(searched, "dockbay/alpha")
        public = self.client.get(
            "/organizations/dockbay/repositories/",
            {"visibility": "public"},
        )
        self.assertContains(public, "dockbay/alpha")
        self.assertNotContains(public, "dockbay/secret")

    def test_owner_sees_every_organization_repository(self):
        self.client.login(username="milan", password="milan-pass-1")

        response = self.client.get("/organizations/dockbay/repositories/")

        for repository in (self.public, self.readable, self.hidden):
            self.assertContains(response, repository.full_name)

    def test_nonmember_cannot_open_the_organization_repository_list(self):
        self.client.login(username="luka", password="luka-pass-word-1")

        self.assertEqual(
            self.client.get("/organizations/dockbay/repositories/").status_code,
            404,
        )


class OrganizationRepositoryDetailTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.reader = User.objects.create_user(username="ana", password="ana-member-pass-1")
        self.outsider = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.organization = create_organization(self.owner, "dockbay")
        self.organization.members.add(self.reader)
        self.public = create_repository(self.organization, "public", Repository.Visibility.PUBLIC)
        self.private = create_repository(self.organization, "private")
        Tag.objects.create(repository=self.private, name="latest", author="Milan")
        grant(
            self.organization,
            self.private,
            self.reader,
            TeamRepositoryPermission.AccessLevel.READ,
            "readers",
        )

    def test_public_repository_is_visible_to_anonymous_and_unrelated_visitors(self):
        path = "/organizations/dockbay/repositories/public/"

        self.assertContains(self.client.get(path), "dockbay/public")
        self.client.login(username="luka", password="luka-pass-word-1")
        self.assertContains(self.client.get(path), "The public image.")

    def test_private_repository_is_concealed_without_read_access(self):
        path = "/organizations/dockbay/repositories/private/"

        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.login(username="luka", password="luka-pass-word-1")
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_read_member_and_owner_can_view_private_repository_and_tags(self):
        path = "/organizations/dockbay/repositories/private/"
        self.client.login(username="ana", password="ana-member-pass-1")

        reader_response = self.client.get(path)
        self.assertContains(reader_response, "dockbay/private:latest")
        self.assertNotContains(reader_response, "New push")
        self.assertNotContains(reader_response, ">Settings<")

        self.client.login(username="milan", password="milan-pass-1")
        owner_response = self.client.get(path)
        self.assertContains(owner_response, "New push")
        self.assertContains(owner_response, ">Settings<")


class OrganizationRepositoryPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.reader = User.objects.create_user(username="ana", password="ana-member-pass-1")
        self.writer = User.objects.create_user(username="iva", password="iva-member-pass-1")
        self.admin = User.objects.create_user(username="marko", password="marko-admin-pass-1")
        self.outsider = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.organization = create_organization(self.owner, "dockbay")
        self.organization.members.add(self.reader, self.writer, self.admin)
        self.repository = create_repository(self.organization, "api")
        self.tag = Tag.objects.create(repository=self.repository, name="latest", author="Milan")
        for user, access, team_name in (
            (self.reader, TeamRepositoryPermission.AccessLevel.READ, "readers"),
            (self.writer, TeamRepositoryPermission.AccessLevel.WRITE, "writers"),
            (self.admin, TeamRepositoryPermission.AccessLevel.ADMIN, "admins"),
        ):
            grant(self.organization, self.repository, user, access, team_name)
        self.detail_path = "/organizations/dockbay/repositories/api/"
        self.tag_path = f"{self.detail_path}tags/new/"
        self.settings_path = f"{self.detail_path}settings/"
        self.delete_path = f"{self.detail_path}delete/"

    def test_read_access_allows_viewing_but_blocks_mutations(self):
        self.client.login(username="ana", password="ana-member-pass-1")

        self.assertEqual(self.client.get(self.detail_path).status_code, 200)
        self.assertEqual(
            self.client.post(
                self.tag_path,
                {"image_name": "dockbay/api", "author": "Ana", "tag": "1.0"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f"{self.detail_path}tags/latest/delete/").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                self.settings_path,
                {"description": "Taken.", "visibility": "public"},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.post(self.delete_path).status_code, 403)
        self.repository.refresh_from_db()
        self.assertEqual(self.repository.description, "The api image.")
        self.assertTrue(Tag.objects.filter(pk=self.tag.pk).exists())

    def test_write_access_manages_tags_but_not_settings_or_repository(self):
        self.client.login(username="iva", password="iva-member-pass-1")

        detail = self.client.get(self.detail_path)
        self.assertContains(detail, "New push")
        self.assertNotContains(detail, ">Settings<")
        created = self.client.post(
            self.tag_path,
            {"image_name": "dockbay/api", "author": "Iva", "tag": "1.0"},
        )
        self.assertRedirects(created, self.detail_path)
        deleted = self.client.post(f"{self.detail_path}tags/latest/delete/")
        self.assertRedirects(deleted, self.detail_path)
        self.assertTrue(Tag.objects.filter(repository=self.repository, name="1.0").exists())
        self.assertFalse(Tag.objects.filter(pk=self.tag.pk).exists())
        self.assertEqual(
            self.client.post(
                self.settings_path,
                {"description": "Taken.", "visibility": "public"},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.post(self.delete_path).status_code, 403)
        self.assertTrue(Repository.objects.filter(pk=self.repository.pk).exists())

    def test_admin_access_manages_tags_settings_and_repository(self):
        self.client.login(username="marko", password="marko-admin-pass-1")

        detail = self.client.get(self.detail_path)
        self.assertContains(detail, "New push")
        self.assertContains(detail, ">Settings<")
        created = self.client.post(
            self.tag_path,
            {"image_name": "dockbay/api", "author": "Marko", "tag": "1.0"},
        )
        self.assertRedirects(created, self.detail_path)
        changed = self.client.post(
            self.settings_path,
            {"description": "Updated.", "visibility": "public"},
        )
        self.assertRedirects(changed, self.detail_path)
        self.repository.refresh_from_db()
        self.assertEqual(self.repository.description, "Updated.")
        deleted = self.client.post(self.delete_path)
        self.assertRedirects(deleted, "/organizations/dockbay/repositories/")
        self.assertFalse(Repository.objects.filter(pk=self.repository.pk).exists())
        self.assertFalse(Tag.objects.exists())
        self.assertFalse(TeamRepositoryPermission.objects.exists())

    def test_organization_owner_has_full_access(self):
        self.client.login(username="milan", password="milan-pass-1")

        pushed = self.client.post(
            self.tag_path,
            {"image_name": "dockbay/api", "author": "Milan", "tag": "1.0"},
        )
        self.assertRedirects(pushed, self.detail_path)
        changed = self.client.post(
            self.settings_path,
            {"description": "Owner update.", "visibility": "private"},
        )
        self.assertRedirects(changed, self.detail_path)
        deleted = self.client.post(self.delete_path)
        self.assertRedirects(deleted, "/organizations/dockbay/repositories/")
        self.assertFalse(Repository.objects.filter(pk=self.repository.pk).exists())

    def test_public_visibility_alone_does_not_grant_mutation(self):
        self.repository.visibility = Repository.Visibility.PUBLIC
        self.repository.save()
        self.client.login(username="luka", password="luka-pass-word-1")

        self.assertEqual(self.client.get(self.detail_path).status_code, 200)
        for path in (self.tag_path, self.settings_path, self.delete_path):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path).status_code, 403)
        self.assertTrue(Repository.objects.filter(pk=self.repository.pk).exists())
        self.assertTrue(Tag.objects.filter(pk=self.tag.pk).exists())

    def test_highest_team_permission_controls_mutations(self):
        grant(
            self.organization,
            self.repository,
            self.reader,
            TeamRepositoryPermission.AccessLevel.ADMIN,
            "reader-admins",
        )
        self.client.login(username="ana", password="ana-member-pass-1")

        response = self.client.post(
            self.settings_path,
            {"description": "Highest wins.", "visibility": "private"},
        )

        self.assertRedirects(response, self.detail_path)
        self.repository.refresh_from_db()
        self.assertEqual(self.repository.description, "Highest wins.")

    def test_unauthenticated_mutation_redirects_to_login(self):
        self.assertRedirects(
            self.client.post(self.tag_path),
            f"/login/?next={self.tag_path}",
        )


class OrganizationRepositoryExploreTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="milan",
            password="milan-pass-1",
            verified_publisher=True,
        )
        self.organization = create_organization(self.owner, "dockbay")
        self.public = create_repository(self.organization, "api", Repository.Visibility.PUBLIC)
        self.private = create_repository(self.organization, "secret")
        self.personal = Repository.objects.create(
            owner=self.owner,
            name="personal",
            description="A personal image.",
            visibility=Repository.Visibility.PUBLIC,
        )

    def test_public_organization_repository_appears_with_the_correct_link(self):
        response = self.client.get("/explore/", {"q": "dockbay"})

        self.assertContains(response, "dockbay/api")
        self.assertContains(response, 'href="/organizations/dockbay/repositories/api/"')
        self.assertNotContains(response, "dockbay/secret")
        self.assertEqual(
            [repository.full_name for repository in search_public_repositories("dockbay")],
            ["dockbay/api"],
        )

    def test_organization_repository_does_not_inherit_user_badges(self):
        response = self.client.get("/explore/", {"badge": "verified"})

        self.assertContains(response, self.personal.full_name)
        self.assertNotContains(response, self.public.full_name)
