def account_role(user):
    if not getattr(user, "is_authenticated", False):
        return "anonymous"
    if user.is_superuser or user.is_staff:
        return "administrator"
    return "ordinary user"
