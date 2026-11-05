from django.shortcuts import render

from registry.search import BADGE_FILTERS, search_public_repositories


def explore(request):
    query = request.GET.get("q", "")
    badge = request.GET.get("badge", "")
    if badge not in BADGE_FILTERS:
        badge = ""
    return render(
        request,
        "registry/explore.html",
        {
            "repositories": search_public_repositories(query, badge),
            "query": query.strip(),
            "badge": badge,
            "badges": BADGE_FILTERS,
        },
    )
