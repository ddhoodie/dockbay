def is_administrator(user):
    return bool(
        getattr(user, "is_authenticated", False) and (user.is_superuser or user.is_staff)
    )


def account_role(user):
    if not getattr(user, "is_authenticated", False):
        return "anonymous"
    if is_administrator(user):
        return "administrator"
    return "ordinary user"
