from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from registry.forms import (
    BadgeAssignmentForm,
    CreateAdministratorForm,
    LogSearchForm,
    ProfileForm,
    RegisterForm,
)
from registry.health import health_status
from registry.logs import LogSearchUnavailable, search_logs
from registry.models import User
from registry.roles import is_administrator
from registry.search import search_ordinary_users


def health(request):
    return HttpResponse(health_status())


def home(request):
    return render(request, "registry/home.html")


@login_required
def profile(request, username):
    subject = get_object_or_404(User, username=username)
    if request.method == "POST" and request.user != subject:
        return HttpResponseForbidden("You can edit only your own profile.")

    form = ProfileForm(request.POST or None, instance=subject)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("profile", username=subject.username)
    return render(
        request,
        "registry/profile.html",
        {"subject": subject, "form": form, "can_edit": request.user == subject},
    )


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


@login_required
def user_badges(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("Only administrators can assign user badges.")

    query = request.GET.get("q", request.POST.get("q", "")).strip()
    form = BadgeAssignmentForm(request.POST or None)
    assigned = False
    if request.method == "POST" and form.is_valid():
        form.save()
        form = BadgeAssignmentForm()
        assigned = True
    return render(
        request,
        "registry/user_badges.html",
        {
            "users": search_ordinary_users(query),
            "query": query,
            "form": form,
            "assigned": assigned,
        },
    )


@login_required
def log_search(request):
    if not is_administrator(request.user):
        return HttpResponseForbidden("Only administrators can search application logs.")

    form = LogSearchForm(request.GET or None)
    results = []
    unavailable = False
    if request.GET and form.is_valid():
        try:
            results = search_logs(form.elasticsearch_query)
        except LogSearchUnavailable:
            unavailable = True
    return render(
        request,
        "registry/log_search.html",
        {"form": form, "results": results, "unavailable": unavailable},
    )


def _after_login(user):
    if user.must_change_password:
        return "change_password"
    return "home"
