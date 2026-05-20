from __future__ import annotations

from httpx import AsyncClient

from app.config import get_settings
from tests.conftest import (
    auth_headers,
    bootstrap_tenant_admin,
    extract_token_from_email,
    latest_email_job,
    login_user,
    unique_email,
    verify_latest_email_token,
)


async def test_password_strength_rejects_weak_password(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": unique_email("weak"),
            "password": "password",
            "name": "Weak Password",
            "role": "tenant_admin",
            "tenant_name": "Weak Shop",
            "tenant_slug": "weak-shop",
        },
    )
    assert response.status_code == 422


async def test_register_login_refresh_logout_flow(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client)
    login_payload = await login_user(
        client,
        email="owner@arzanshop.kz",
        password="Secur3P@ss!",
    )

    products_response = await client.get(
        "/v1/products",
        headers=auth_headers(login_payload["access_token"]),
    )
    assert products_response.status_code == 200
    assert products_response.json()["data"] == []

    refresh_response = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["access_token"]
    assert refreshed["refresh_token"] != login_payload["refresh_token"]

    old_refresh_response = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert old_refresh_response.status_code == 401
    assert old_refresh_response.json()["code"] == "REFRESH_TOKEN_REVOKED"

    new_refresh_response = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": refreshed["refresh_token"]},
    )
    assert new_refresh_response.status_code == 200

    logout_response = await client.post(
        "/v1/auth/logout",
        headers=auth_headers(refreshed["access_token"]),
        json={"refresh_token": new_refresh_response.json()["refresh_token"]},
    )
    assert logout_response.status_code == 204


async def test_protected_endpoint_rejects_missing_token(client: AsyncClient) -> None:
    response = await client.get("/v1/products")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_invalid_cursor_returns_standard_400(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client)
    tokens = await login_user(client, email="owner@arzanshop.kz", password="Secur3P@ss!")

    response = await client.get(
        "/v1/products?cursor=not-a-valid-cursor",
        headers=auth_headers(tokens["access_token"]),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_CURSOR"


async def test_login_rate_limit_after_five_attempts(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client)

    for _ in range(5):
        response = await client.post(
            "/v1/auth/login",
            json={"email": "owner@arzanshop.kz", "password": "WrongP@ss1"},
        )
        assert response.status_code == 401

    throttled = await client.post(
        "/v1/auth/login",
        json={"email": "owner@arzanshop.kz", "password": "WrongP@ss1"},
    )
    assert throttled.status_code == 429
    assert throttled.json()["code"] == "RATE_LIMIT_EXCEEDED"


async def test_register_rate_limit_after_five_attempts(client: AsyncClient) -> None:
    for idx in range(5):
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": unique_email(f"owner{idx}"),
                "password": "Secur3P@ss!",
                "name": "Tenant Owner",
                "role": "tenant_admin",
                "tenant_name": f"Shop {idx}",
                "tenant_slug": f"shop-{idx}",
            },
        )
        assert response.status_code == 201

    throttled = await client.post(
        "/v1/auth/register",
        json={
            "email": unique_email("owner-final"),
            "password": "Secur3P@ss!",
            "name": "Tenant Owner",
            "role": "tenant_admin",
            "tenant_name": "Shop Final",
            "tenant_slug": "shop-final",
        },
    )
    assert throttled.status_code == 429
    assert throttled.json()["code"] == "RATE_LIMIT_EXCEEDED"


async def test_unverified_user_is_blocked_from_business_routes(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client, verify_email=False)
    tokens = await login_user(client, email="owner@arzanshop.kz", password="Secur3P@ss!")

    blocked = await client.get("/v1/products", headers=auth_headers(tokens["access_token"]))
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "EMAIL_NOT_VERIFIED"

    verification_token = await verify_latest_email_token(
        client,
        recipient_email="owner@arzanshop.kz",
        purpose="email_verification",
        token_label="Verification token",
        endpoint="/v1/auth/verify-email",
    )

    allowed = await client.get("/v1/products", headers=auth_headers(tokens["access_token"]))
    assert allowed.status_code == 200

    reused = await client.post("/v1/auth/verify-email", json={"token": verification_token})
    assert reused.status_code == 400
    assert reused.json()["code"] == "INVALID_VERIFICATION_TOKEN"


async def test_master_verification_token_verifies_registered_email(
    client: AsyncClient,
    monkeypatch,
) -> None:
    master_token = "leanstock-demo-email-verify-2026"
    user_email = unique_email("master-verify")
    monkeypatch.setenv("EMAIL_VERIFICATION_MASTER_TOKEN", master_token)
    get_settings.cache_clear()
    try:
        await bootstrap_tenant_admin(
            client,
            email=user_email,
            tenant_slug=f"master-verify-{user_email.split('@')[0].split('-')[-1]}",
            verify_email=False,
        )

        verify_response = await client.post(
            "/v1/auth/verify-email",
            json={"token": master_token, "email": user_email},
        )
        assert verify_response.status_code == 200, verify_response.text

        tokens = await login_user(client, email=user_email, password="Secur3P@ss!")
        products_response = await client.get(
            "/v1/products",
            headers=auth_headers(tokens["access_token"]),
        )
        assert products_response.status_code == 200
    finally:
        get_settings.cache_clear()


async def test_password_reset_token_flow(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client)

    request_response = await client.post(
        "/v1/auth/password-reset/request",
        json={"email": "owner@arzanshop.kz"},
    )
    assert request_response.status_code == 200

    job = await latest_email_job("owner@arzanshop.kz", "password_reset")
    reset_token = extract_token_from_email(job, "Reset token")

    confirm_response = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "N3wSecur3P@ss!"},
    )
    assert confirm_response.status_code == 200

    reused = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "Another3P@ss!"},
    )
    assert reused.status_code == 400
    assert reused.json()["code"] == "INVALID_RESET_TOKEN"

    old_login = await client.post(
        "/v1/auth/login",
        json={"email": "owner@arzanshop.kz", "password": "Secur3P@ss!"},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/v1/auth/login",
        json={"email": "owner@arzanshop.kz", "password": "N3wSecur3P@ss!"},
    )
    assert new_login.status_code == 200
