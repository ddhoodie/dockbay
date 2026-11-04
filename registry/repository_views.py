from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from registry.forms import RepositoryCreateForm, RepositorySettingsForm
from registry.models import Repository


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


@login_required
def repository_detail(request, username, name):
    repository = _visible_repository(request, username, name)
    return render(request, "registry/repository_detail.html", {"repository": repository})


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
