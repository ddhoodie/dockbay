from django.db.models import Case, IntegerField, Q, Value, When

from registry.models import Repository, User

BADGE_FILTERS = {
    "official": "Docker Official Image",
    "verified": "Verified Publisher",
    "sponsored": "Sponsored OSS",
}


def search_ordinary_users(query):
    users = User.objects.filter(is_staff=False, is_superuser=False)
    query = query.strip()
    if query:
        users = users.filter(username__icontains=query)
    return users.order_by("username")


def search_public_repositories(query, badge=""):
    repositories = Repository.objects.filter(
        visibility=Repository.Visibility.PUBLIC,
    ).select_related("owner")
    if badge == "official":
        repositories = repositories.filter(official=True)
    elif badge == "verified":
        repositories = repositories.filter(owner__verified_publisher=True)
    elif badge == "sponsored":
        repositories = repositories.filter(owner__sponsored_oss=True)
    query = query.strip()
    if not query:
        return repositories.order_by("owner__username", "name")
    return (
        repositories.filter(
            Q(name__icontains=query)
            | Q(owner__username__icontains=query)
            | Q(description__icontains=query)
        )
        .annotate(
            relevance=Case(
                When(name__iexact=query, then=Value(3)),
                When(name__icontains=query, then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("-relevance", "owner__username", "name")
    )
