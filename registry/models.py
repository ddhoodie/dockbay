from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


class User(AbstractUser):
    display_name = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    must_change_password = models.BooleanField(default=False)


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
