import tempfile
from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from registry.forms import OrganizationCreateForm, OrganizationSettingsForm
from registry.models import Organization, User


def uploaded_image(name="organization.png", color="blue"):
    content = BytesIO()
    Image.new("RGB", (2, 2), color).save(content, "PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")


class TemporaryMediaTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()
        super().tearDown()


class OrganizationModelAndFormTests(TemporaryMediaTestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")

    def test_creation_records_fields_and_adds_the_owner_as_a_member(self):
        organization = Organization.objects.create(
            owner=self.owner,
            name="dockbay",
            description="A container community.",
            image=uploaded_image("user-controlled.png"),
        )

        self.assertEqual(organization.owner, self.owner)
        self.assertEqual(organization.name, "dockbay")
        self.assertEqual(organization.description, "A container community.")
        self.assertEqual(list(organization.members.all()), [self.owner])
        self.assertTrue(organization.image.name.startswith("organizations/"))
        self.assertNotIn("user-controlled", organization.image.name)

    def test_name_and_image_validation_are_form_errors(self):
        Organization.objects.create(
            owner=self.owner,
            name="dockbay",
            description="Existing.",
            image=uploaded_image(),
        )
        other = User.objects.create_user(username="ana", password="ana-admin-pass-1")

        duplicate = OrganizationCreateForm(
            other,
            data={"name": "dockbay", "description": "Duplicate."},
            files={"image": uploaded_image("duplicate.png")},
        )
        invalid_name = OrganizationCreateForm(
            other,
            data={"name": "Not Valid", "description": "Invalid name."},
            files={"image": uploaded_image("valid.png")},
        )
        invalid_image = OrganizationCreateForm(
            other,
            data={"name": "another", "description": "Invalid image."},
            files={
                "image": SimpleUploadedFile(
                    "not-an-image.png",
                    b"not an image",
                    content_type="image/png",
                )
            },
        )

        self.assertFalse(duplicate.is_valid())
        self.assertIn("name", duplicate.errors)
        self.assertFalse(invalid_name.is_valid())
        self.assertIn("name", invalid_name.errors)
        self.assertFalse(invalid_image.is_valid())
        self.assertIn("image", invalid_image.errors)

    def test_duplicate_membership_is_harmless_and_the_owner_cannot_be_removed(self):
        organization = Organization.objects.create(
            owner=self.owner,
            name="dockbay",
            description="A container community.",
            image=uploaded_image(),
        )

        organization.members.add(self.owner, self.owner)
        organization.members.remove(self.owner)
        self.owner.organizations.remove(organization)

        self.assertEqual(organization.members.filter(pk=self.owner.pk).count(), 1)
        with self.assertRaises(ValidationError):
            organization.members.clear()

    def test_settings_expose_only_description_and_image(self):
        organization = Organization.objects.create(
            owner=self.owner,
            name="dockbay",
            description="Before.",
            image=uploaded_image(),
        )

        form = OrganizationSettingsForm(
            data={"name": "renamed", "description": "After.", "owner": 999},
            instance=organization,
        )

        self.assertEqual(list(form.fields), ["description", "image"])
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.name, "dockbay")
        self.assertEqual(saved.owner, self.owner)
        self.assertEqual(saved.description, "After.")

    def test_deleting_the_owner_deletes_the_organization_and_image(self):
        organization = Organization.objects.create(
            owner=self.owner,
            name="dockbay",
            description="A container community.",
            image=uploaded_image(),
        )
        image_path = Path(organization.image.path)

        with self.captureOnCommitCallbacks(execute=True):
            self.owner.delete()

        self.assertFalse(Organization.objects.filter(pk=organization.pk).exists())
        self.assertFalse(image_path.exists())


class OrganizationPageTests(TemporaryMediaTestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="milan", password="milan-pass-1")
        self.member = User.objects.create_user(username="ana", password="ana-member-pass-1")
        self.candidate = User.objects.create_user(username="candidate", password="candidate-pass-1")
        self.other = User.objects.create_user(username="luka", password="luka-pass-word-1")
        self.administrator = User.objects.create_user(
            username="administrator",
            password="administrator-pass-1",
            is_staff=True,
        )
        self.inactive = User.objects.create_user(
            username="inactive",
            password="inactive-pass-1",
            is_active=False,
        )
        self.organization = Organization.objects.create(
            owner=self.owner,
            name="dockbay",
            description="A container community.",
            image=uploaded_image(),
        )
        self.organization.members.add(self.member)
        self.client.login(username="milan", password="milan-pass-1")

    def test_an_authenticated_user_creates_and_opens_an_organization(self):
        response = self.client.post(
            "/organizations/new/",
            {
                "name": "harbor",
                "description": "Another community.",
                "image": uploaded_image("harbor.png", "green"),
            },
        )

        self.assertRedirects(response, "/organizations/harbor/")
        organization = Organization.objects.get(name="harbor")
        self.assertEqual(organization.owner, self.owner)
        self.assertTrue(organization.members.filter(pk=self.owner.pk).exists())
        detail = self.client.get("/organizations/harbor/")
        self.assertContains(detail, "Another community.")
        self.assertContains(detail, organization.image.url)
        self.assertContains(self.client.get("/"), "Organizations")

        duplicate = self.client.post(
            "/organizations/new/",
            {
                "name": "harbor",
                "description": "Duplicate.",
                "image": uploaded_image("duplicate.png"),
            },
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, "already exists")
        self.assertEqual(Organization.objects.filter(name="harbor").count(), 1)

    def test_an_administrator_cannot_create_an_organization(self):
        self.client.login(username="administrator", password="administrator-pass-1")

        self.assertEqual(self.client.get("/organizations/new/").status_code, 403)
        response = self.client.post(
            "/organizations/new/",
            {
                "name": "admin-owned",
                "description": "Not allowed.",
                "image": uploaded_image("admin.png"),
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Organization.objects.filter(name="admin-owned").exists())

    def test_list_shows_only_organizations_the_user_belongs_to(self):
        unrelated = Organization.objects.create(
            owner=self.other,
            name="unrelated",
            description="Not Milan's organization.",
            image=uploaded_image("unrelated.png"),
        )

        owner_list = self.client.get("/organizations/")
        self.assertContains(owner_list, "dockbay")
        self.assertNotContains(owner_list, unrelated.name)

        self.client.login(username="ana", password="ana-member-pass-1")
        self.assertContains(self.client.get("/organizations/"), "dockbay")

        self.client.login(username="candidate", password="candidate-pass-1")
        candidate_list = self.client.get("/organizations/")
        self.assertNotContains(candidate_list, "/organizations/dockbay/")
        self.assertNotContains(candidate_list, f"/organizations/{unrelated.name}/")

    def test_member_sees_details_and_the_full_member_list_but_not_owner_actions(self):
        self.client.login(username="ana", password="ana-member-pass-1")

        detail = self.client.get("/organizations/dockbay/")
        self.assertContains(detail, "A container community.")
        self.assertContains(detail, "Owner: milan")
        self.assertContains(detail, "Members")
        self.assertNotContains(detail, "Settings")
        self.assertNotContains(detail, "Deactivate")

        members = self.client.get("/organizations/dockbay/members/")
        self.assertContains(members, "milan (owner)")
        self.assertContains(members, "ana")
        self.assertNotContains(members, "Add a member")

    def test_nonmember_cannot_open_details_or_members(self):
        self.client.login(username="candidate", password="candidate-pass-1")

        self.assertEqual(self.client.get("/organizations/dockbay/").status_code, 404)
        self.assertEqual(self.client.get("/organizations/dockbay/members/").status_code, 404)

    def test_owner_edits_description_and_image_but_not_name_or_owner(self):
        old_image = Path(self.organization.image.path)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/organizations/dockbay/settings/",
                {
                    "name": "renamed",
                    "description": "Updated community.",
                    "owner": self.other.pk,
                    "image": uploaded_image("updated.png", "red"),
                },
            )

        self.assertRedirects(response, "/organizations/dockbay/")
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "dockbay")
        self.assertEqual(self.organization.owner, self.owner)
        self.assertEqual(self.organization.description, "Updated community.")
        self.assertFalse(old_image.exists())
        self.assertTrue(Path(self.organization.image.path).exists())

    def test_member_cannot_edit_even_with_a_crafted_post(self):
        self.client.login(username="ana", password="ana-member-pass-1")

        response = self.client.post(
            "/organizations/dockbay/settings/",
            {"description": "Taken.", "image": uploaded_image("taken.png")},
        )

        self.assertEqual(response.status_code, 403)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.description, "A container community.")

    def test_owner_searches_eligible_users_case_insensitively(self):
        response = self.client.get("/organizations/dockbay/members/", {"q": "CAND"})

        self.assertContains(response, "candidate")
        self.assertNotContains(response, "ana-member-pass-1")
        self.assertNotContains(response, "candidate-pass-1")
        self.assertNotContains(response, "administrator")
        self.assertNotContains(response, "inactive")
        self.assertNotIn(self.member, response.context["candidates"])

    def test_owner_adds_a_member_and_repeating_the_post_is_safe(self):
        response = self.client.post(
            "/organizations/dockbay/members/",
            {"user": self.candidate.pk},
        )

        self.assertRedirects(response, "/organizations/dockbay/members/")
        self.assertTrue(self.organization.members.filter(pk=self.candidate.pk).exists())

        repeated = self.client.post(
            "/organizations/dockbay/members/",
            {"user": self.candidate.pk},
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(self.organization.members.filter(pk=self.candidate.pk).count(), 1)

    def test_nonowners_and_disallowed_accounts_cannot_be_added(self):
        self.client.login(username="ana", password="ana-member-pass-1")
        self.assertEqual(
            self.client.post(
                "/organizations/dockbay/members/",
                {"user": self.candidate.pk},
            ).status_code,
            403,
        )

        self.client.login(username="candidate", password="candidate-pass-1")
        self.assertEqual(
            self.client.post(
                "/organizations/dockbay/members/",
                {"user": self.other.pk},
            ).status_code,
            404,
        )

        self.client.login(username="milan", password="milan-pass-1")
        for disallowed in (self.administrator, self.inactive):
            response = self.client.post(
                "/organizations/dockbay/members/",
                {"user": disallowed.pk},
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(self.organization.members.filter(pk=disallowed.pk).exists())

    def test_owner_deactivates_the_organization_and_cleans_memberships_and_image(self):
        organization_id = self.organization.pk
        image_path = Path(self.organization.image.path)
        membership_model = Organization.members.through

        confirmation = self.client.get("/organizations/dockbay/deactivate/")
        self.assertContains(confirmation, "permanently removes")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/organizations/dockbay/deactivate/")

        self.assertRedirects(response, "/organizations/")
        self.assertFalse(Organization.objects.filter(pk=organization_id).exists())
        self.assertFalse(membership_model.objects.filter(organization_id=organization_id).exists())
        self.assertFalse(image_path.exists())

    def test_member_cannot_deactivate_the_organization(self):
        self.client.login(username="ana", password="ana-member-pass-1")

        self.assertEqual(self.client.get("/organizations/dockbay/deactivate/").status_code, 403)
        self.assertEqual(self.client.post("/organizations/dockbay/deactivate/").status_code, 403)
        self.assertTrue(Organization.objects.filter(pk=self.organization.pk).exists())

    def test_anonymous_users_are_redirected_from_organization_pages(self):
        self.client.logout()

        for path in (
            "/organizations/",
            "/organizations/new/",
            "/organizations/dockbay/",
            "/organizations/dockbay/settings/",
            "/organizations/dockbay/members/",
            "/organizations/dockbay/deactivate/",
        ):
            response = self.client.get(path)
            self.assertRedirects(response, f"/login/?next={path}")
