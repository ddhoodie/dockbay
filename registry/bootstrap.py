import secrets
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model

SUPERADMIN_USERNAME = "superadmin"


def create_initial_superadmin():
    User = get_user_model()
    existing = User.objects.filter(is_superuser=True).first()
    if existing is not None:
        return existing

    password = secrets.token_urlsafe(16)
    user = User.objects.create_superuser(
        username=SUPERADMIN_USERNAME,
        password=password,
        must_change_password=True,
    )
    path = Path(settings.SUPERADMIN_PASSWORD_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"username={user.username}\npassword={password}\n",
        encoding="utf-8",
    )
    return user


def bootstrap_on_migrate(sender, **kwargs):
    if settings.SKIP_SUPERADMIN_BOOTSTRAP:
        return
    create_initial_superadmin()
