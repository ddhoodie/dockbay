from django.contrib.auth.views import LogoutView
from django.urls import path

from registry.views import (
    change_password,
    create_administrator,
    health,
    home,
    login_view,
)

urlpatterns = [
    path("", home, name="home"),
    path("health/", health, name="health"),
    path("login/", login_view, name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("password/change/", change_password, name="change_password"),
    path("administrators/new/", create_administrator, name="create_administrator"),
]
