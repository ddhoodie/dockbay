from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError


class CreateAdministratorForm(forms.Form):
    username = forms.CharField(max_length=150, label="Korisničko ime")
    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Lozinka",
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        UnicodeUsernameValidator()(username)
        if get_user_model().objects.filter(username=username).exists():
            raise ValidationError("Korisničko ime je zauzeto.")
        return username

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password
