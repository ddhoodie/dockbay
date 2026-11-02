from django.urls import path

from registry.views import health

urlpatterns = [
    path("health/", health, name="health"),
]
