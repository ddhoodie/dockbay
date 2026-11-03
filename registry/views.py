from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render

from registry.forms import CreateAdministratorForm, RegisterForm
from registry.health import health_status
from registry.models import User


def health(request):
    return HttpResponse(health_status())


def home(request):
    return render(request, "registry/home.html")


def register(request):
    if request.user.is_authenticated:
        return redirect(_after_login(request.user))

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        User.objects.create_user(
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        return redirect("login")
    return render(request, "registry/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_after_login(request.user))

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect(_after_login(user))
    return render(request, "registry/login.html", {"form": form})


@login_required
def change_password(request):
    form = PasswordChangeForm(request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        update_session_auth_hash(request, user)
        return redirect("home")
    return render(request, "registry/change_password.html", {"form": form})


@login_required
def create_administrator(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Only the superadmin can add an administrator.")

    form = CreateAdministratorForm(request.POST or None)
    created = False
    if request.method == "POST" and form.is_valid():
        User.objects.create_user(
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
            is_staff=True,
        )
        created = True
        form = CreateAdministratorForm()
    return render(
        request,
        "registry/create_administrator.html",
        {"form": form, "created": created},
    )


def _after_login(user):
    if user.must_change_password:
        return "change_password"
    return "home"
