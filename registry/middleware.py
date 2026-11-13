import logging

from django.shortcuts import redirect
from django.urls import reverse


request_logger = logging.getLogger("dockbay.requests")


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except Exception:
            self._log(request, 500)
            raise

        self._log(request, response.status_code)
        return response

    @staticmethod
    def _log(request, status):
        if status >= 500:
            level = logging.ERROR
        elif status >= 400:
            level = logging.WARNING
        else:
            level = logging.INFO
        request_logger.log(
            level,
            "request completed method=%s path=%s status=%s",
            request.method,
            request.path,
            status,
        )


class MustChangePasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        allowed = {reverse("change_password"), reverse("logout")}
        if (
            user is not None
            and user.is_authenticated
            and user.must_change_password
            and request.path not in allowed
        ):
            return redirect("change_password")
        return self.get_response(request)
