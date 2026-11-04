from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from registry.forms import RepositoryCreateForm, RepositorySettingsForm, TagPushForm
from registry.models import Repository, Tag


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
    return render(
        request,
        "registry/repository_detail.html",
        {
            "repository": repository,
            "tags": tags,
            "name": tag_name,
            "sort": sort,
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
