from fastapi import HTTPException


def canonical_company_id(repositories, company_id):
    if not repositories:
        return company_id
    return str(repositories["invoices"].mapper.resolve("company", company_id))


def canonical_gstin_id(repositories, gstin_id):
    if not repositories:
        return gstin_id
    return str(repositories["invoices"].mapper.resolve("gstin", gstin_id))


def canonical_user_id(repositories, user_id):
    if not repositories:
        return user_id
    return str(repositories["invoices"].mapper.resolve("user", user_id))


def enforce_company_scope(user, company_id, *, repositories=None, demo_mode=False):
    if demo_mode:
        if user.get("company_id") != company_id:
            raise HTTPException(403, "Cross-company access denied")
        return

    try:
        requested = canonical_company_id(repositories, company_id)
        user_company = canonical_company_id(repositories, user.get("company_id"))
    except (ValueError, TypeError):
        raise HTTPException(403, "Cross-company access denied")

    if requested != user_company:
        raise HTTPException(403, "Cross-company access denied")
