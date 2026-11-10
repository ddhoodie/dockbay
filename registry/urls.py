from django.contrib.auth.views import LogoutView
from django.urls import path

from registry.explore_views import explore
from registry.organization_views import (
    organization_create,
    organization_deactivate,
    organization_detail,
    organization_list,
    organization_members,
    organization_settings,
)
from registry.repository_views import (
    repository_create,
    repository_delete,
    repository_detail,
    repository_list,
    repository_settings,
    tag_create,
    tag_delete,
)
from registry.views import (
    change_password,
    create_administrator,
    health,
    home,
    login_view,
    profile,
    register,
    user_badges,
)

urlpatterns = [
    path("", home, name="home"),
    path("explore/", explore, name="explore"),
    path("organizations/", organization_list, name="organization_list"),
    path("organizations/new/", organization_create, name="organization_create"),
    path("organizations/<str:name>/", organization_detail, name="organization_detail"),
    path(
        "organizations/<str:name>/settings/",
        organization_settings,
        name="organization_settings",
    ),
    path(
        "organizations/<str:name>/members/",
        organization_members,
        name="organization_members",
    ),
    path(
        "organizations/<str:name>/deactivate/",
        organization_deactivate,
        name="organization_deactivate",
    ),
    path("users/<str:username>/", profile, name="profile"),
    path("repositories/", repository_list, name="repository_list"),
    path("repositories/new/", repository_create, name="repository_create"),
    path("repositories/<str:username>/<str:name>/", repository_detail, name="repository_detail"),
    path(
        "repositories/<str:username>/<str:name>/settings/",
        repository_settings,
        name="repository_settings",
    ),
    path(
        "repositories/<str:username>/<str:name>/delete/",
        repository_delete,
        name="repository_delete",
    ),
    path(
        "repositories/<str:username>/<str:name>/tags/new/",
        tag_create,
        name="tag_create",
    ),
    path(
        "repositories/<str:username>/<str:name>/tags/<str:tag>/delete/",
        tag_delete,
        name="tag_delete",
    ),
    path("health/", health, name="health"),
    path("login/", login_view, name="login"),
    path("register/", register, name="register"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("password/change/", change_password, name="change_password"),
    path("administrators/new/", create_administrator, name="create_administrator"),
    path("administrators/users/", user_badges, name="user_badges"),
]
