from pathlib import Path
from uuid import uuid4

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver


class User(AbstractUser):
    display_name = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    must_change_password = models.BooleanField(default=False)
    verified_publisher = models.BooleanField(default=False)
    sponsored_oss = models.BooleanField(default=False)


def organization_image_path(_instance, filename):
    return f"organizations/{uuid4().hex}{Path(filename).suffix.lower()}"


class Organization(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="owned_organizations",
    )
    members = models.ManyToManyField(User, related_name="organizations")
    name = models.CharField(
        max_length=255,
        unique=True,
        validators=[
            RegexValidator(
                r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
                "Use lowercase letters, digits, and . _ -",
            )
        ],
    )
    description = models.CharField(max_length=255)
    image = models.ImageField(upload_to=organization_image_path)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        old_image = None
        if self.pk:
            old_image = type(self).objects.filter(pk=self.pk).values_list("image", flat=True).first()
        super().save(*args, **kwargs)
        self.members.add(self.owner)
        if old_image and old_image != self.image.name:
            storage = self.image.storage
            transaction.on_commit(lambda: storage.delete(old_image))

    def __str__(self):
        return self.name


class Team(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="teams",
    )
    name = models.CharField(
        max_length=255,
        validators=[
            RegexValidator(
                r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
                "Use lowercase letters, digits, and . _ -",
            )
        ],
    )
    description = models.CharField(max_length=255)
    members = models.ManyToManyField(User, related_name="teams")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_team_name_per_organization",
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


@receiver(post_delete, sender=Organization)
def delete_organization_image(sender, instance, **_kwargs):
    if instance.image:
        storage = instance.image.storage
        image_name = instance.image.name
        transaction.on_commit(lambda: storage.delete(image_name))


@receiver(m2m_changed, sender=Organization.members.through)
def keep_owner_as_member(sender, instance, action, reverse, pk_set, **_kwargs):
    if action == "pre_remove":
        if reverse:
            owned = Organization.objects.filter(owner=instance, pk__in=pk_set)
            pk_set.difference_update(owned.values_list("pk", flat=True))
        else:
            pk_set.discard(instance.owner_id)
    elif action == "pre_clear":
        owns_membership = (
            Organization.objects.filter(owner=instance, members=instance).exists()
            if reverse
            else True
        )
        if owns_membership:
            raise ValidationError("The organization owner must remain a member.")
    elif action in {"post_remove", "post_clear"}:
        if reverse:
            Team.members.through.objects.filter(user_id=instance.pk).exclude(
                team__organization__members=instance,
            ).delete()
        elif pk_set:
            Team.members.through.objects.filter(
                team__organization=instance,
                user_id__in=pk_set,
            ).delete()


@receiver(m2m_changed, sender=Team.members.through)
def keep_team_members_in_organization(sender, instance, action, reverse, pk_set, **_kwargs):
    if action != "pre_add":
        return
    if reverse:
        allowed = Team.objects.filter(
            pk__in=pk_set,
            organization__members=instance,
        ).values_list("pk", flat=True)
    else:
        allowed = instance.organization.members.filter(pk__in=pk_set).values_list("pk", flat=True)
    if set(pk_set) - set(allowed):
        raise ValidationError("Team members must belong to the organization.")


class Repository(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="repositories",
        blank=True,
        null=True,
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="repositories",
        blank=True,
        null=True,
    )
    name = models.CharField(
        max_length=255,
        validators=[
            RegexValidator(
                r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
                "Use lowercase letters, digits, and . _ -",
            )
        ],
    )
    description = models.CharField(max_length=255)
    visibility = models.CharField(max_length=7, choices=Visibility.choices)
    official = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        official=True,
                        owner__isnull=True,
                        organization__isnull=True,
                    )
                    | (
                        models.Q(official=False)
                        & (
                            models.Q(owner__isnull=False, organization__isnull=True)
                            | models.Q(owner__isnull=True, organization__isnull=False)
                        )
                    )
                ),
                name="repository_owner_matches_official_flag",
            ),
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_repository_name_per_owner",
                condition=models.Q(owner__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_repository_name_per_organization",
                condition=models.Q(organization__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["name"],
                name="unique_official_repository_name",
                condition=models.Q(official=True),
            ),
        ]
        ordering = ["name"]

    def clean(self):
        super().clean()
        if self.official:
            if self.owner_id is not None or self.organization_id is not None:
                raise ValidationError("An official repository has no user or organization owner.")
            return
        if (self.owner_id is None) == (self.organization_id is None):
            raise ValidationError("A repository must have exactly one user or organization owner.")

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        if self.official:
            return self.name
        namespace = self.owner.username if self.owner_id else self.organization.name
        return f"{namespace}/{self.name}"

    def get_absolute_url(self):
        from django.urls import reverse

        if self.official:
            return reverse("official_repository_detail", kwargs={"name": self.name})
        if self.organization_id:
            return reverse(
                "organization_repository_detail",
                kwargs={"name": self.organization.name, "repository_name": self.name},
            )
        return reverse(
            "repository_detail",
            kwargs={"username": self.owner.username, "name": self.name},
        )

    def get_settings_url(self):
        from django.urls import reverse

        if self.official:
            return reverse("official_repository_settings", kwargs={"name": self.name})
        if self.organization_id:
            return reverse(
                "organization_repository_settings",
                kwargs={"name": self.organization.name, "repository_name": self.name},
            )
        return reverse(
            "repository_settings",
            kwargs={"username": self.owner.username, "name": self.name},
        )

    def get_delete_url(self):
        from django.urls import reverse

        if self.official:
            return reverse("official_repository_delete", kwargs={"name": self.name})
        if self.organization_id:
            return reverse(
                "organization_repository_delete",
                kwargs={"name": self.organization.name, "repository_name": self.name},
            )
        return reverse(
            "repository_delete",
            kwargs={"username": self.owner.username, "name": self.name},
        )

    def get_tag_create_url(self):
        from django.urls import reverse

        if self.official:
            return reverse("official_tag_create", kwargs={"name": self.name})
        if self.organization_id:
            return reverse(
                "organization_tag_create",
                kwargs={"name": self.organization.name, "repository_name": self.name},
            )
        return reverse(
            "tag_create",
            kwargs={"username": self.owner.username, "name": self.name},
        )

    def get_tag_delete_url(self, tag_name):
        from django.urls import reverse

        if self.official:
            return reverse(
                "official_tag_delete",
                kwargs={"name": self.name, "tag": tag_name},
            )
        if self.organization_id:
            return reverse(
                "organization_tag_delete",
                kwargs={
                    "name": self.organization.name,
                    "repository_name": self.name,
                    "tag": tag_name,
                },
            )
        return reverse(
            "tag_delete",
            kwargs={"username": self.owner.username, "name": self.name, "tag": tag_name},
        )

    @property
    def star_count(self):
        return 0

    @property
    def badges(self):
        labels = []
        if self.official:
            labels.append("Docker Official Image")
        if self.owner_id and self.owner.verified_publisher:
            labels.append("Verified Publisher")
        if self.owner_id and self.owner.sponsored_oss:
            labels.append("Sponsored OSS")
        return labels


class TeamRepositoryPermission(models.Model):
    class AccessLevel(models.IntegerChoices):
        READ = 1, "Read-only"
        WRITE = 2, "Read+write"
        ADMIN = 3, "Admin"

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="repository_permissions",
    )
    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="team_permissions",
    )
    access = models.PositiveSmallIntegerField(choices=AccessLevel.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "repository"],
                name="unique_team_repository_permission",
            )
        ]
        ordering = ["repository__name", "team__name"]

    def clean(self):
        super().clean()
        if self.repository_id and self.repository.organization_id is None:
            raise ValidationError("Team permissions require an organization repository.")
        if (
            self.team_id
            and self.repository_id
            and self.team.organization_id != self.repository.organization_id
        ):
            raise ValidationError("The team and repository must belong to the same organization.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


def effective_repository_access(user, repository):
    if repository.organization_id is None or not getattr(user, "is_authenticated", False):
        return None
    if repository.organization.owner_id == user.id:
        return TeamRepositoryPermission.AccessLevel.ADMIN
    if not repository.organization.members.filter(pk=user.pk).exists():
        return None
    access = (
        TeamRepositoryPermission.objects.filter(repository=repository, team__members=user)
        .order_by("-access")
        .values_list("access", flat=True)
        .first()
    )
    return TeamRepositoryPermission.AccessLevel(access) if access else None


def has_repository_access(user, repository, minimum):
    access = effective_repository_access(user, repository)
    return access is not None and access >= minimum


class Tag(models.Model):
    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="tags",
    )
    name = models.CharField(
        max_length=128,
        validators=[
            RegexValidator(
                r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$",
                "Use letters, digits, and . _ -, starting with a letter, digit, or _.",
            )
        ],
    )
    author = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "name"],
                name="unique_tag_name_per_repository",
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return f"{self.repository.full_name}:{self.name}"

    def get_delete_url(self):
        return self.repository.get_tag_delete_url(self.name)
