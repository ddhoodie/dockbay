from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from registry.forms import TeamForm, TeamMemberForm, TeamRepositoryPermissionForm
from registry.models import Team
from registry.organization_views import _member_organization, _owned_organization


@login_required
def team_list(request, name):
    organization = _member_organization(request, name)
    return render(
        request,
        "registry/team_list.html",
        {
            "organization": organization,
            "teams": organization.teams.all(),
            "is_owner": organization.owner_id == request.user.id,
        },
    )


@login_required
def team_create(request, name):
    organization = _owned_organization(request, name)
    form = TeamForm(organization, request.POST or None)
    if request.method == "POST" and form.is_valid():
        team = form.save()
        return redirect("team_detail", name=organization.name, team_name=team.name)
    return render(
        request,
        "registry/team_form.html",
        {"organization": organization, "form": form, "heading": "New team", "submit_label": "Create"},
    )


@login_required
def team_detail(request, name, team_name):
    organization = _member_organization(request, name)
    team = get_object_or_404(Team, organization=organization, name=team_name)
    return _render_team(request, team)


@login_required
def team_edit(request, name, team_name):
    organization = _owned_organization(request, name)
    team = get_object_or_404(Team, organization=organization, name=team_name)
    form = TeamForm(organization, request.POST or None, instance=team)
    if request.method == "POST" and form.is_valid():
        team = form.save()
        return redirect("team_detail", name=organization.name, team_name=team.name)
    return render(
        request,
        "registry/team_form.html",
        {
            "organization": organization,
            "form": form,
            "heading": f"Edit {team.name}",
            "submit_label": "Save",
        },
    )


@login_required
@require_POST
def team_add_member(request, name, team_name):
    organization = _owned_organization(request, name)
    team = get_object_or_404(Team, organization=organization, name=team_name)
    form = TeamMemberForm(team, request.POST)
    if form.is_valid():
        form.save()
        return redirect("team_detail", name=organization.name, team_name=team.name)
    return _render_team(request, team, member_form=form)


@login_required
@require_POST
def team_permission(request, name, team_name):
    organization = _owned_organization(request, name)
    team = get_object_or_404(Team, organization=organization, name=team_name)
    form = TeamRepositoryPermissionForm(team, request.POST)
    if form.is_valid():
        form.save()
        return redirect("team_detail", name=organization.name, team_name=team.name)
    return _render_team(request, team, permission_form=form)


def _render_team(request, team, member_form=None, permission_form=None):
    is_owner = team.organization.owner_id == request.user.id
    return render(
        request,
        "registry/team_detail.html",
        {
            "organization": team.organization,
            "team": team,
            "members": team.members.order_by("username"),
            "permissions": team.repository_permissions.select_related("repository"),
            "is_owner": is_owner,
            "member_form": member_form or (TeamMemberForm(team) if is_owner else None),
            "permission_form": permission_form
            or (TeamRepositoryPermissionForm(team) if is_owner else None),
        },
    )
