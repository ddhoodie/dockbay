from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from registry.forms import (
    OrganizationCreateForm,
    OrganizationMemberForm,
    OrganizationSettingsForm,
)
from registry.models import Organization


@login_required
def organization_list(request):
    organizations = Organization.objects.filter(members=request.user)
    return render(
        request,
        "registry/organization_list.html",
        {"organizations": organizations},
    )


@login_required
def organization_create(request):
    if request.user.is_staff or request.user.is_superuser:
        raise PermissionDenied("Only ordinary users can create organizations.")
    form = OrganizationCreateForm(
        request.user,
        request.POST or None,
        request.FILES or None,
    )
    if request.method == "POST" and form.is_valid():
        organization = form.save()
        return redirect("organization_detail", name=organization.name)
    return render(
        request,
        "registry/organization_form.html",
        {"form": form, "heading": "New organization", "submit_label": "Create"},
    )


@login_required
def organization_detail(request, name):
    organization = _member_organization(request, name)
    return render(
        request,
        "registry/organization_detail.html",
        {"organization": organization},
    )


@login_required
def organization_settings(request, name):
    organization = _owned_organization(request, name)
    form = OrganizationSettingsForm(
        request.POST or None,
        request.FILES or None,
        instance=organization,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("organization_detail", name=organization.name)
    return render(
        request,
        "registry/organization_form.html",
        {
            "form": form,
            "heading": f"Settings for {organization.name}",
            "submit_label": "Save",
        },
    )


@login_required
def organization_members(request, name):
    organization = _member_organization(request, name)
    is_owner = organization.owner_id == request.user.id
    if request.method == "POST" and not is_owner:
        raise PermissionDenied("Only the owner can add organization members.")

    form = OrganizationMemberForm(organization, request.POST or None) if is_owner else None
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("organization_members", name=organization.name)

    query = request.GET.get("q", "").strip()
    candidates = form.fields["user"].queryset if form else organization.members.none()
    if query and form:
        candidates = candidates.filter(username__icontains=query)
    return render(
        request,
        "registry/organization_members.html",
        {
            "organization": organization,
            "members": organization.members.order_by("username"),
            "is_owner": is_owner,
            "form": form,
            "candidates": candidates,
            "query": query,
        },
    )


@login_required
def organization_deactivate(request, name):
    organization = _owned_organization(request, name)
    if request.method == "POST":
        organization.delete()
        return redirect("organization_list")
    return render(
        request,
        "registry/organization_deactivate.html",
        {"organization": organization},
    )


def _member_organization(request, name):
    try:
        return Organization.objects.get(name=name, members=request.user)
    except Organization.DoesNotExist as error:
        raise Http404 from error


def _owned_organization(request, name):
    organization = get_object_or_404(Organization, name=name)
    if organization.owner_id != request.user.id:
        raise PermissionDenied("Only the owner can change this organization.")
    return organization
