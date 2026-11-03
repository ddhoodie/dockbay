def account_role(user):
    if not getattr(user, "is_authenticated", False):
        return "neautentifikovan"
    if user.is_superuser or user.is_staff:
        return "administrator"
    return "običan korisnik"
