from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from registry.forms import TeamForm
from registry.models import (
    Organization,
    Repository,
    Team,
    TeamRepositoryPermission,
    User,
    effective_repository_access,
    has_repository_access,
)


def create_organization(owner, name):
    return Organization.objects.create(
        owner=owner,
        name=name,
        description=f"The {name} organization.",
        image=f"organizations/{name}.png",
    )


def create_organization_repository(organization, name="api"):
    return Repository.objects.create(
        organization=organization,
        name=name,
        description="An organization image.",
        visibility=Repository.Visibility.PRIVATE,
    )


class TeamModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.member = User.objects.create_user(username="ana", password="ana-member-pass-1")
        self.outsider = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.organization = create_organization(self.owner, "dockbay")
        self.organization.members.add(self.member)

    def test_team_names_are_unique_only_inside_one_organization(self):
        Team.objects.create(organization=self.organization, name="backend", description="API team.")
        other = create_organization(self.outsider, "harbor")

        Team.objects.create(organization=other, name="backend", description="Other API team.")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Team.objects.create(
                    organization=self.organization,
                    name="backend",
                    description="Duplicate.",
                )

        self.assertEqual(self.organization.teams.get().organization, self.organization)

    def test_team_form_reports_a_duplicate_name_and_cannot_change_organization(self):
        team = Team.objects.create(
            organization=self.organization,
            name="backend",
            description="API team.",
        )
        other = create_organization(self.outsider, "harbor")
        duplicate = TeamForm(
            self.organization,
            data={"name": "backend", "description": "Duplicate."},
        )
        edited = TeamForm(
            self.organization,
            data={"name": "platform", "description": "Updated."},
            instance=team,
        )

        self.assertFalse(duplicate.is_valid())
        self.assertIn("name", duplicate.errors)
        self.assertTrue(edited.is_valid(), edited.errors)
        saved = edited.save()
        self.assertEqual(saved.organization, self.organization)
        self.assertNotEqual(saved.organization, other)

    def test_only_organization_members_can_join_and_duplicates_are_harmless(self):
        team = Team.objects.create(
            organization=self.organization,
            name="backend",
            description="API team.",
        )

        team.members.add(self.member, self.member)
        self.assertEqual(team.members.filter(pk=self.member.pk).count(), 1)
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                team.members.add(self.outsider)
        self.assertFalse(self.organization.members.filter(pk=self.outsider.pk).exists())

    def test_removing_an_organization_member_removes_their_team_memberships(self):
        team = Team.objects.create(
            organization=self.organization,
            name="backend",
            description="API team.",
        )
        team.members.add(self.member)

        self.organization.members.remove(self.member)

        self.assertFalse(team.members.filter(pk=self.member.pk).exists())

    def test_deleting_an_organization_deletes_its_teams(self):
        Team.objects.create(
            organization=self.organization,
            name="backend",
            description="API team.",
        )

        self.organization.delete()

        self.assertFalse(Team.objects.exists())


class RepositoryOwnershipTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.other = User.objects.create_user(username="ana", password="ana-member-pass-1")
        self.organization = create_organization(self.owner, "dockbay")

    def test_personal_and_organization_repositories_keep_their_full_names(self):
        personal = Repository.objects.create(
            owner=self.owner,
            name="api",
            description="A personal image.",
            visibility=Repository.Visibility.PUBLIC,
        )
        organization = create_organization_repository(self.organization)

        self.assertEqual(personal.full_name, "milan/api")
        self.assertEqual(organization.full_name, "dockbay/api")
        self.assertEqual(organization.badges, [])

    def test_repository_requires_exactly_one_owner_type(self):
        values = {
            "name": "api",
            "description": "An image.",
            "visibility": Repository.Visibility.PUBLIC,
        }
        for owners in ({}, {"owner": self.owner, "organization": self.organization}):
            with self.subTest(owners=owners):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Repository.objects.create(**owners, **values)

    def test_repository_names_are_unique_inside_each_owner_namespace(self):
        Repository.objects.create(
            owner=self.owner,
            name="api",
            description="Personal.",
            visibility=Repository.Visibility.PUBLIC,
        )
        create_organization_repository(self.organization)
        other_organization = create_organization(self.other, "harbor")

        Repository.objects.create(
            owner=self.other,
            name="api",
            description="Other personal.",
            visibility=Repository.Visibility.PUBLIC,
        )
        create_organization_repository(other_organization)
        for owner in ({"owner": self.owner}, {"organization": self.organization}):
            with self.subTest(owner=owner):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Repository.objects.create(
                            **owner,
                            name="api",
                            description="Duplicate.",
                            visibility=Repository.Visibility.PUBLIC,
                        )


class TeamPermissionModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.other_owner = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.organization = create_organization(self.owner, "dockbay")
        self.other_organization = create_organization(self.other_owner, "harbor")
        self.team = Team.objects.create(
            organization=self.organization,
            name="backend",
            description="API team.",
        )
        self.repository = create_organization_repository(self.organization)

    def test_access_levels_have_an_explicit_order_and_labels(self):
        levels = TeamRepositoryPermission.AccessLevel

        self.assertLess(levels.READ, levels.WRITE)
        self.assertLess(levels.WRITE, levels.ADMIN)
        self.assertEqual(levels.READ.label, "Read-only")
        self.assertEqual(levels.WRITE.label, "Read+write")
        self.assertEqual(levels.ADMIN.label, "Admin")

    def test_one_team_has_only_one_permission_for_a_repository(self):
        TeamRepositoryPermission.objects.create(
            team=self.team,
            repository=self.repository,
            access=TeamRepositoryPermission.AccessLevel.READ,
        )

        with self.assertRaises(ValidationError):
            TeamRepositoryPermission.objects.create(
                team=self.team,
                repository=self.repository,
                access=TeamRepositoryPermission.AccessLevel.WRITE,
            )

    def test_personal_and_cross_organization_permissions_are_rejected(self):
        personal = Repository.objects.create(
            owner=self.owner,
            name="personal",
            description="Personal.",
            visibility=Repository.Visibility.PUBLIC,
        )
        other = create_organization_repository(self.other_organization)

        for repository in (personal, other):
            with self.subTest(repository=repository.full_name):
                with self.assertRaises(ValidationError):
                    TeamRepositoryPermission.objects.create(
                        team=self.team,
                        repository=repository,
                        access=TeamRepositoryPermission.AccessLevel.READ,
                    )

    def test_deleting_a_team_repository_or_organization_cascades_permissions(self):
        for target in ("team", "repository", "organization"):
            with self.subTest(target=target):
                team = Team.objects.create(
                    organization=self.organization,
                    name=target,
                    description="Temporary team.",
                )
                repository = create_organization_repository(self.organization, target)
                TeamRepositoryPermission.objects.create(
                    team=team,
                    repository=repository,
                    access=TeamRepositoryPermission.AccessLevel.READ,
                )
                if target == "team":
                    team.delete()
                elif target == "repository":
                    repository.delete()
                else:
                    self.organization.delete()
                self.assertFalse(
                    TeamRepositoryPermission.objects.filter(
                        team_id=team.pk,
                        repository_id=repository.pk,
                    ).exists()
                )
                if target == "organization":
                    break


class EffectiveRepositoryAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.member = User.objects.create_user(username="ana", password="ana-member-pass-1")
        self.no_team = User.objects.create_user(username="iva", password="iva-member-pass-1")
        self.outsider = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.organization = create_organization(self.owner, "dockbay")
        self.organization.members.add(self.member, self.no_team)
        self.repository = create_organization_repository(self.organization)

    def grant(self, name, access):
        team = Team.objects.create(
            organization=self.organization,
            name=name,
            description=f"{name} team.",
        )
        team.members.add(self.member)
        TeamRepositoryPermission.objects.create(
            team=team,
            repository=self.repository,
            access=access,
        )
        return team

    def test_owner_is_admin_and_users_without_a_grant_have_no_access(self):
        levels = TeamRepositoryPermission.AccessLevel

        self.assertEqual(effective_repository_access(self.owner, self.repository), levels.ADMIN)
        self.assertIsNone(effective_repository_access(self.no_team, self.repository))
        self.assertIsNone(effective_repository_access(self.outsider, self.repository))

    def test_read_write_and_admin_capabilities_match_the_required_matrix(self):
        levels = TeamRepositoryPermission.AccessLevel
        for granted, expected in (
            (levels.READ, (True, False, False)),
            (levels.WRITE, (True, True, False)),
            (levels.ADMIN, (True, True, True)),
        ):
            with self.subTest(granted=granted):
                TeamRepositoryPermission.objects.all().delete()
                self.organization.teams.all().delete()
                self.grant(f"team-{granted}", granted)
                self.assertEqual(
                    (
                        has_repository_access(self.member, self.repository, levels.READ),
                        has_repository_access(self.member, self.repository, levels.WRITE),
                        has_repository_access(self.member, self.repository, levels.ADMIN),
                    ),
                    expected,
                )

    def test_multiple_teams_resolve_to_the_highest_access(self):
        levels = TeamRepositoryPermission.AccessLevel
        self.grant("readers", levels.READ)
        self.grant("writers", levels.WRITE)
        self.grant("admins", levels.ADMIN)

        self.assertEqual(effective_repository_access(self.member, self.repository), levels.ADMIN)

    def test_personal_repository_authorization_is_not_replaced_by_team_access(self):
        personal = Repository.objects.create(
            owner=self.owner,
            name="personal",
            description="Personal.",
            visibility=Repository.Visibility.PRIVATE,
        )

        self.assertIsNone(effective_repository_access(self.owner, personal))
        self.client.login(username="milan", password="milan-pass-1")
        self.assertEqual(self.client.get("/repositories/milan/personal/").status_code, 200)
        self.client.login(username="ana", password="ana-member-pass-1")
        self.assertEqual(self.client.get("/repositories/milan/personal/").status_code, 404)


class TeamPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.member = User.objects.create_user(username="ana", password="ana-member-pass-1")
        self.candidate = User.objects.create_user(username="iva", password="iva-member-pass-1")
        self.outsider = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.administrator = User.objects.create_user(
            username="administrator",
            password="administrator-pass-1",
            is_staff=True,
        )
        self.organization = create_organization(self.owner, "dockbay")
        self.organization.members.add(self.member, self.candidate)
        self.team = Team.objects.create(
            organization=self.organization,
            name="backend",
            description="API team.",
        )
        self.team.members.add(self.member)
        self.repository = create_organization_repository(self.organization)
        self.other_organization = create_organization(self.outsider, "harbor")
        self.other_repository = create_organization_repository(self.other_organization)
        self.personal = Repository.objects.create(
            owner=self.owner,
            name="personal",
            description="Personal.",
            visibility=Repository.Visibility.PUBLIC,
        )
        self.client.login(username="milan", password="milan-pass-1")

    def test_member_lists_and_opens_teams_without_owner_controls(self):
        self.client.login(username="ana", password="ana-member-pass-1")

        listed = self.client.get("/organizations/dockbay/teams/")
        detail = self.client.get("/organizations/dockbay/teams/backend/")

        self.assertContains(listed, "backend")
        self.assertNotContains(listed, "New team")
        self.assertContains(detail, "API team.")
        self.assertContains(detail, "ana")
        self.assertNotContains(detail, ">Edit<")
        self.assertNotContains(detail, "Add a member")
        self.assertNotContains(detail, "Assign repository access")

    def test_nonmember_cannot_list_or_open_teams(self):
        self.client.login(username="luka", password="luka-pass-word-1")

        self.assertEqual(self.client.get("/organizations/dockbay/teams/").status_code, 404)
        self.assertEqual(
            self.client.get("/organizations/dockbay/teams/backend/").status_code,
            404,
        )

    def test_owner_creates_and_edits_a_team_with_friendly_duplicate_errors(self):
        created = self.client.post(
            "/organizations/dockbay/teams/new/",
            {"name": "frontend", "description": "Web team."},
        )
        self.assertRedirects(created, "/organizations/dockbay/teams/frontend/")

        duplicate = self.client.post(
            "/organizations/dockbay/teams/new/",
            {"name": "frontend", "description": "Duplicate."},
        )
        self.assertContains(duplicate, "already has a team")

        edited = self.client.post(
            "/organizations/dockbay/teams/frontend/edit/",
            {"name": "platform", "description": "Platform team."},
        )
        self.assertRedirects(edited, "/organizations/dockbay/teams/platform/")
        team = Team.objects.get(name="platform")
        self.assertEqual(team.description, "Platform team.")
        self.assertEqual(team.organization, self.organization)

    def test_member_cannot_create_or_edit_teams(self):
        self.client.login(username="ana", password="ana-member-pass-1")

        self.assertEqual(
            self.client.post(
                "/organizations/dockbay/teams/new/",
                {"name": "taken", "description": "Taken."},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/organizations/dockbay/teams/backend/edit/",
                {"name": "taken", "description": "Taken."},
            ).status_code,
            403,
        )
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "backend")

    def test_owner_adds_only_eligible_organization_members(self):
        added = self.client.post(
            "/organizations/dockbay/teams/backend/members/",
            {"user": self.candidate.pk},
        )
        self.assertRedirects(added, "/organizations/dockbay/teams/backend/")
        self.assertTrue(self.team.members.filter(pk=self.candidate.pk).exists())

        repeated = self.client.post(
            "/organizations/dockbay/teams/backend/members/",
            {"user": self.candidate.pk},
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(self.team.members.filter(pk=self.candidate.pk).count(), 1)

        for disallowed in (self.outsider, self.administrator):
            with self.subTest(user=disallowed.username):
                response = self.client.post(
                    "/organizations/dockbay/teams/backend/members/",
                    {"user": disallowed.pk},
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(self.team.members.filter(pk=disallowed.pk).exists())

    def test_team_member_cannot_add_users(self):
        self.client.login(username="ana", password="ana-member-pass-1")

        response = self.client.post(
            "/organizations/dockbay/teams/backend/members/",
            {"user": self.candidate.pk},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.team.members.filter(pk=self.candidate.pk).exists())

    def test_owner_assigns_and_updates_repository_access_without_duplicates(self):
        path = "/organizations/dockbay/teams/backend/permissions/"
        assigned = self.client.post(
            path,
            {"repository": self.repository.pk, "access": TeamRepositoryPermission.AccessLevel.READ},
        )
        self.assertRedirects(assigned, "/organizations/dockbay/teams/backend/")
        changed = self.client.post(
            path,
            {"repository": self.repository.pk, "access": TeamRepositoryPermission.AccessLevel.ADMIN},
        )
        self.assertRedirects(changed, "/organizations/dockbay/teams/backend/")

        permission = TeamRepositoryPermission.objects.get()
        self.assertEqual(permission.access, TeamRepositoryPermission.AccessLevel.ADMIN)
        self.assertContains(self.client.get("/organizations/dockbay/teams/backend/"), "Admin")

    def test_permission_post_rejects_personal_and_other_organization_repositories(self):
        path = "/organizations/dockbay/teams/backend/permissions/"
        for repository in (self.personal, self.other_repository):
            with self.subTest(repository=repository.full_name):
                response = self.client.post(
                    path,
                    {"repository": repository.pk, "access": TeamRepositoryPermission.AccessLevel.READ},
                )
                self.assertEqual(response.status_code, 200)
        self.assertFalse(TeamRepositoryPermission.objects.exists())

    def test_nonowner_cannot_assign_permissions(self):
        self.client.login(username="ana", password="ana-member-pass-1")

        response = self.client.post(
            "/organizations/dockbay/teams/backend/permissions/",
            {"repository": self.repository.pk, "access": TeamRepositoryPermission.AccessLevel.WRITE},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(TeamRepositoryPermission.objects.exists())

    def test_anonymous_users_are_redirected_from_team_pages(self):
        self.client.logout()

        for path in (
            "/organizations/dockbay/teams/",
            "/organizations/dockbay/teams/new/",
            "/organizations/dockbay/teams/backend/",
            "/organizations/dockbay/teams/backend/edit/",
        ):
            self.assertRedirects(self.client.get(path), f"/login/?next={path}")


class TeamRegressionTests(TestCase):
    def test_organization_deactivation_cascades_teams_permissions_and_repositories(self):
        owner = User.objects.create_user(username="milan", password="milan-pass-1")
        organization = create_organization(owner, "dockbay")
        team = Team.objects.create(
            organization=organization,
            name="backend",
            description="API team.",
        )
        repository = create_organization_repository(organization)
        TeamRepositoryPermission.objects.create(
            team=team,
            repository=repository,
            access=TeamRepositoryPermission.AccessLevel.ADMIN,
        )
        self.client.login(username="milan", password="milan-pass-1")

        response = self.client.post("/organizations/dockbay/deactivate/")

        self.assertRedirects(response, "/organizations/")
        self.assertFalse(Team.objects.exists())
        self.assertFalse(TeamRepositoryPermission.objects.exists())
        self.assertFalse(Repository.objects.exists())

    def test_explore_and_badges_ignore_organization_repositories_without_crashing(self):
        owner = User.objects.create_user(username="milan", password="milan-pass-1")
        organization = create_organization(owner, "dockbay")
        organization_repository = create_organization_repository(organization)
        personal = Repository.objects.create(
            owner=owner,
            name="personal",
            description="Personal.",
            visibility=Repository.Visibility.PUBLIC,
        )

        self.assertEqual(organization_repository.badges, [])
        response = self.client.get("/explore/")
        self.assertContains(response, personal.full_name)
        self.assertNotContains(response, organization_repository.full_name)
