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


class Repository(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="repositories",
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
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_repository_name_per_owner",
            )
        ]
        ordering = ["name"]

    @property
    def full_name(self):
        return f"{self.owner.username}/{self.name}"

    @property
    def star_count(self):
        return 0

    @property
    def badges(self):
        labels = []
        if self.official:
            labels.append("Docker Official Image")
        if self.owner.verified_publisher:
            labels.append("Verified Publisher")
        if self.owner.sponsored_oss:
            labels.append("Sponsored OSS")
        return labels


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
