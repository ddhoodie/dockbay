from django.shortcuts import redirect
from django.urls import reverse


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
