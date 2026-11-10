from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from registry.forms import (
    OrganizationRepositoryCreateForm,
    RepositoryCreateForm,
    RepositorySettingsForm,
    TagPushForm,
)
from registry.models import Repository, Tag, TeamRepositoryPermission, has_repository_access
from registry.organization_views import _member_organization


@login_required
def repository_list(request):
    repositories = Repository.objects.filter(owner=request.user)
    name = request.GET.get("name", "").strip()
    visibility = request.GET.get("visibility", "")
    if name:
        repositories = repositories.filter(name__icontains=name)
    if visibility in Repository.Visibility.values:
        repositories = repositories.filter(visibility=visibility)
    return render(
        request,
        "registry/repository_list.html",
        {
            "repositories": repositories,
            "name": name,
            "visibility": visibility,
        },
    )


@login_required
def repository_create(request):
    form = RepositoryCreateForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        repository = form.save()
        return redirect("repository_detail", username=request.user.username, name=repository.name)
    return render(request, "registry/repository_form.html", {"form": form})


def repository_detail(request, username, name):
    repository = _visible_repository(request, username, name)
    return _render_repository_detail(request, repository)


@login_required
def organization_repository_list(request, name):
    organization = _member_organization(request, name)
    repositories = organization.repositories.select_related("organization")
    repository_name = request.GET.get("name", "").strip()
    visibility = request.GET.get("visibility", "")
    if repository_name:
        repositories = repositories.filter(name__icontains=repository_name)
    if visibility in Repository.Visibility.values:
        repositories = repositories.filter(visibility=visibility)
    repositories = [
        repository
        for repository in repositories
        if repository.visibility == Repository.Visibility.PUBLIC
        or has_repository_access(
            request.user,
            repository,
            TeamRepositoryPermission.AccessLevel.READ,
        )
    ]
    return render(
        request,
        "registry/repository_list.html",
        {
            "organization": organization,
            "repositories": repositories,
            "name": repository_name,
            "visibility": visibility,
        },
    )


@login_required
def organization_repository_create(request, name):
    organization = _member_organization(request, name)
    form = OrganizationRepositoryCreateForm(organization, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("organization_repository_list", name=organization.name)
    return render(
        request,
        "registry/repository_form.html",
        {"form": form, "organization": organization},
    )


def organization_repository_detail(request, name, repository_name):
    repository = _visible_organization_repository(request, name, repository_name)
    return _render_repository_detail(request, repository)


def _render_repository_detail(request, repository):
    tag_name = request.GET.get("name", "").strip()
    sort = request.GET.get("sort", "name")
    tags = repository.tags.all()
    if tag_name:
        tags = tags.filter(name__icontains=tag_name)
    if sort == "created":
        tags = tags.order_by("-created_at", "name")
    else:
        sort = "name"
        tags = tags.order_by("name")
    can_write, can_admin = _repository_capabilities(request.user, repository)
    return render(
        request,
        "registry/repository_detail.html",
        {
            "repository": repository,
            "tags": tags,
            "name": tag_name,
            "sort": sort,
            "can_write": can_write,
            "can_admin": can_admin,
        },
    )


@login_required
def tag_create(request, username, name):
    repository = _changeable_repository(request, username, name)
    form = TagPushForm(repository, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("repository_detail", username=username, name=repository.name)
    return render(request, "registry/tag_form.html", {"form": form, "repository": repository})


@login_required
def tag_delete(request, username, name, tag):
    repository = _changeable_repository(request, username, name)
    image_tag = get_object_or_404(Tag, repository=repository, name=tag)
    if request.method == "POST":
        image_tag.delete()
        return redirect("repository_detail", username=username, name=repository.name)
    return render(
        request,
        "registry/tag_delete.html",
        {"repository": repository, "tag": image_tag},
    )


@login_required
def repository_settings(request, username, name):
    repository = _owned_repository(request, username, name)
    form = RepositorySettingsForm(request.POST or None, instance=repository)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("repository_detail", username=username, name=repository.name)
    return render(
        request,
        "registry/repository_settings.html",
        {"form": form, "repository": repository},
    )


@login_required
def repository_delete(request, username, name):
    repository = _owned_repository(request, username, name)
    if request.method == "POST":
        repository.delete()
        return redirect("repository_list")
    return render(request, "registry/repository_delete.html", {"repository": repository})


@login_required
def organization_tag_create(request, name, repository_name):
    repository = _changeable_organization_repository(
        request,
        name,
        repository_name,
        TeamRepositoryPermission.AccessLevel.WRITE,
    )
    form = TagPushForm(repository, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(
            "organization_repository_detail",
            name=name,
            repository_name=repository.name,
        )
    return render(request, "registry/tag_form.html", {"form": form, "repository": repository})


@login_required
def organization_tag_delete(request, name, repository_name, tag):
    repository = _changeable_organization_repository(
        request,
        name,
        repository_name,
        TeamRepositoryPermission.AccessLevel.WRITE,
    )
    image_tag = get_object_or_404(Tag, repository=repository, name=tag)
    if request.method == "POST":
        image_tag.delete()
        return redirect(
            "organization_repository_detail",
            name=name,
            repository_name=repository.name,
        )
    return render(
        request,
        "registry/tag_delete.html",
        {"repository": repository, "tag": image_tag},
    )


@login_required
def organization_repository_settings(request, name, repository_name):
    repository = _changeable_organization_repository(
        request,
        name,
        repository_name,
        TeamRepositoryPermission.AccessLevel.ADMIN,
    )
    form = RepositorySettingsForm(request.POST or None, instance=repository)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(
            "organization_repository_detail",
            name=name,
            repository_name=repository.name,
        )
    return render(
        request,
        "registry/repository_settings.html",
        {"form": form, "repository": repository},
    )


@login_required
def organization_repository_delete(request, name, repository_name):
    repository = _changeable_organization_repository(
        request,
        name,
        repository_name,
        TeamRepositoryPermission.AccessLevel.ADMIN,
    )
    if request.method == "POST":
        repository.delete()
        return redirect("organization_repository_list", name=name)
    return render(request, "registry/repository_delete.html", {"repository": repository})


def _visible_repository(request, username, name):
    repository = get_object_or_404(Repository, owner__username=username, name=name)
    if repository.owner_id != request.user.id and repository.visibility != Repository.Visibility.PUBLIC:
        raise Http404
    return repository


def _owned_repository(request, username, name):
    repository = get_object_or_404(Repository, owner__username=username, name=name)
    if repository.owner_id != request.user.id:
        raise PermissionDenied("Only the owner can change this repository.")
    return repository


def _changeable_repository(request, username, name):
    repository = _visible_repository(request, username, name)
    if repository.owner_id != request.user.id:
        raise PermissionDenied("Only the owner can change this repository.")
    return repository


def _visible_organization_repository(request, name, repository_name):
    repository = get_object_or_404(
        Repository.objects.select_related("organization"),
        organization__name=name,
        name=repository_name,
    )
    if (
        repository.visibility != Repository.Visibility.PUBLIC
        and not has_repository_access(
            request.user,
            repository,
            TeamRepositoryPermission.AccessLevel.READ,
        )
    ):
        raise Http404
    return repository


def _changeable_organization_repository(request, name, repository_name, minimum):
    repository = _visible_organization_repository(request, name, repository_name)
    if not has_repository_access(request.user, repository, minimum):
        raise PermissionDenied("Your team permission does not allow this change.")
    return repository


def _repository_capabilities(user, repository):
    if repository.owner_id:
        is_owner = repository.owner_id == user.id
        return is_owner, is_owner
    return (
        has_repository_access(user, repository, TeamRepositoryPermission.AccessLevel.WRITE),
        has_repository_access(user, repository, TeamRepositoryPermission.AccessLevel.ADMIN),
    )
