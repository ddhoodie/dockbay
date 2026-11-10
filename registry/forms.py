from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from registry.models import Organization, Repository, Tag
from registry.search import search_ordinary_users


class UsernamePasswordForm(forms.Form):
    username = forms.CharField(max_length=150, label="Username")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")

    def clean_username(self):
        username = self.cleaned_data["username"]
        UnicodeUsernameValidator()(username)
        if get_user_model().objects.filter(username=username).exists():
            raise ValidationError("That username is taken.")
        return username

    def clean_password(self):
        password = self.cleaned_data["password"]
        username = self.data.get("username")
        user = get_user_model()(username=username) if username else None
        validate_password(password, user=user)
        return password


class ProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["display_name", "email", "bio"]
        labels = {
            "display_name": "Display name",
            "email": "Email",
            "bio": "Bio",
        }


class CreateAdministratorForm(UsernamePasswordForm):
    pass


class BadgeAssignmentForm(forms.Form):
    BADGES = (
        ("verified_publisher", "Verified Publisher"),
        ("sponsored_oss", "Sponsored OSS"),
    )

    user = forms.ModelChoiceField(queryset=get_user_model().objects.none())
    badge = forms.ChoiceField(choices=BADGES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = get_user_model().objects.filter(
            is_staff=False,
            is_superuser=False,
        )

    def save(self):
        user = self.cleaned_data["user"]
        badge = self.cleaned_data["badge"]
        setattr(user, badge, True)
        user.save(update_fields=[badge])
        return user


class RegisterForm(UsernamePasswordForm):
    password_confirmation = forms.CharField(
        widget=forms.PasswordInput,
        label="Confirm password",
    )

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirmation = cleaned.get("password_confirmation")
        if password and confirmation and password != confirmation:
            self.add_error("password_confirmation", "Passwords do not match.")
        return cleaned


class OrganizationCreateForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name", "description", "image"]
        labels = {
            "name": "Name",
            "description": "Description",
            "image": "Image",
        }

    def __init__(self, owner, *args, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        organization = super().save(commit=False)
        organization.owner = self.owner
        if commit:
            organization.save()
        return organization


class OrganizationSettingsForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["description", "image"]
        labels = {"description": "Description", "image": "Image"}


class OrganizationMemberForm(forms.Form):
    user = forms.ModelChoiceField(queryset=get_user_model().objects.none())

    def __init__(self, organization, *args, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = search_ordinary_users("").filter(
            is_active=True,
        ).exclude(organizations=organization)

    def save(self):
        user = self.cleaned_data["user"]
        self.organization.members.add(user)
        return user


class RepositoryCreateForm(forms.ModelForm):
    class Meta:
        model = Repository
        fields = ["name", "description", "visibility"]
        labels = {
            "name": "Name",
            "description": "Description",
            "visibility": "Visibility",
        }

    def __init__(self, owner, *args, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"]
        if Repository.objects.filter(owner=self.owner, name=name).exists():
            raise ValidationError("You already have a repository with this name.")
        return name

    def save(self, commit=True):
        repository = super().save(commit=False)
        repository.owner = self.owner
        if commit:
            repository.save()
        return repository


class RepositorySettingsForm(forms.ModelForm):
    class Meta:
        model = Repository
        fields = ["description", "visibility"]
        labels = {
            "description": "Description",
            "visibility": "Visibility",
        }


class TagPushForm(forms.Form):
    image_name = forms.CharField(max_length=406, label="Image name")
    author = forms.CharField(max_length=150, label="Author")
    tag = forms.CharField(max_length=128, label="Tag")

    def __init__(self, repository, *args, **kwargs):
        self.repository = repository
        super().__init__(*args, **kwargs)
        self.fields["image_name"].initial = repository.full_name

    def clean_image_name(self):
        image_name = self.cleaned_data["image_name"].strip()
        if image_name != self.repository.full_name:
            raise ValidationError("That image name does not match this repository.")
        return image_name

    def clean_author(self):
        author = self.cleaned_data["author"].strip()
        if not author:
            raise ValidationError("Enter an author.")
        return author

    def clean_tag(self):
        name = self.cleaned_data["tag"].strip()
        RegexValidator(
            r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$",
            "Use letters, digits, and . _ -, starting with a letter, digit, or _.",
        )(name)
        if Tag.objects.filter(repository=self.repository, name=name).exists():
            raise ValidationError("This repository already has this tag.")
        return name

    def save(self):
        return Tag.objects.create(
            repository=self.repository,
            name=self.cleaned_data["tag"],
            author=self.cleaned_data["author"],
        )
