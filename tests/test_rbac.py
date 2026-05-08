from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import (
    auth_headers,
    bootstrap_tenant_admin,
    login_user,
    verify_latest_email_token,
)


async def test_wrong_role_gets_403_for_product_creation(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client)
    admin_tokens = await login_user(
        client,
        email="owner@arzanshop.kz",
        password="Secur3P@ss!",
    )

    create_staff_response = await client.post(
        "/v1/auth/register",
        headers=auth_headers(admin_tokens["access_token"]),
        json={
            "email": "manager@arzanshop.kz",
            "password": "Secur3P@ss!",
            "name": "Warehouse Manager",
            "role": "warehouse_manager",
        },
    )
    assert create_staff_response.status_code == 201
    await verify_latest_email_token(
        client,
        recipient_email="manager@arzanshop.kz",
        purpose="email_verification",
        token_label="Verification token",
        endpoint="/v1/auth/verify-email",
    )

    manager_tokens = await login_user(
        client,
        email="manager@arzanshop.kz",
        password="Secur3P@ss!",
    )

    forbidden = await client.post(
        "/v1/products",
        headers=auth_headers(manager_tokens["access_token"]),
        json={
            "name": "Classic T-Shirt",
            "category": "Clothing",
            "unit_of_measure": "pcs",
            "variants": [
                {
                    "sku": "TSHIRT-RED-L",
                    "color": "Red",
                    "size": "L",
                    "cost_price": 2100.0,
                    "selling_price": 4990.0,
                    "liquidation_floor_price": 2990.0,
                }
            ],
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
