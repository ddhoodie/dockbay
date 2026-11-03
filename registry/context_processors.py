from registry.roles import account_role


def role(request):
    return {"account_role": account_role(request.user)}
