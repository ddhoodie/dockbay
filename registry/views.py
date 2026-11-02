from django.http import HttpResponse

from registry.health import health_status


def health(request):
    return HttpResponse(health_status())
