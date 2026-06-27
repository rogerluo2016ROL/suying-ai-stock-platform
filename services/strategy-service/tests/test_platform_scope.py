from app.platform_scope import resolve_platform_scope


def test_resolve_platform_scope_uses_headers_and_jwt_subject():
    scope = resolve_platform_scope(
        user={"sub": "7", "role": "user"},
        tenant_id="tenant-alpha",
        account_id="paper-u7",
        data_scope="account",
    )

    assert scope["tenant_id"] == "tenant-alpha"
    assert scope["owner_user_id"] == "7"
    assert scope["account_id"] == "paper-u7"
    assert scope["visibility"] == "private"
    assert scope["data_scope"] == "account"


def test_resolve_platform_scope_falls_back_for_service_or_missing_user():
    scope = resolve_platform_scope(user={"role": "admin"})

    assert scope["tenant_id"] == "platform"
    assert scope["owner_user_id"] == "service"
    assert scope["account_id"] == ""
    assert scope["data_scope"] == "tenant"
