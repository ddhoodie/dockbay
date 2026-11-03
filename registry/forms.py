from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError


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


class CreateAdministratorForm(UsernamePasswordForm):
    pass


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
