from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import auth_headers, bootstrap_tenant_admin, login_user, unique_email


async def _seed_transfer_ready_stock(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    sku: str,
) -> tuple[str, str, str]:
    source_warehouse = await client.post(
        "/v1/warehouses",
        headers=headers,
        json={"name": f"{sku} Source", "location": "Almaty"},
    )
    destination_warehouse = await client.post(
        "/v1/warehouses",
        headers=headers,
        json={"name": f"{sku} Destination", "location": "Astana"},
    )
    assert source_warehouse.status_code == 201, source_warehouse.text
    assert destination_warehouse.status_code == 201, destination_warehouse.text

    product_response = await client.post(
        "/v1/products",
        headers=headers,
        json={
            "name": "Tenant Scoped Product",
            "category": "Clothing",
            "unit_of_measure": "pcs",
            "variants": [
                {
                    "sku": sku,
                    "color": "Black",
                    "size": "M",
                    "cost_price": 1000.0,
                    "selling_price": 2500.0,
                    "liquidation_floor_price": 1500.0,
                }
            ],
        },
    )
    assert product_response.status_code == 201, product_response.text
    variant_id = product_response.json()["variants"][0]["id"]

    stock_response = await client.post(
        "/v1/inventory/adjust",
        headers=headers,
        json={
            "variant_id": variant_id,
            "warehouse_id": source_warehouse.json()["id"],
            "quantity_delta": 3,
            "reason": "surplus",
            "note": "Tenant isolation stock seed",
        },
    )
    assert stock_response.status_code == 200, stock_response.text
    return source_warehouse.json()["id"], destination_warehouse.json()["id"], variant_id


async def test_transfer_atomicity_prevents_overselling(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client)
    tokens = await login_user(client, email="owner@arzanshop.kz", password="Secur3P@ss!")
    headers = auth_headers(tokens["access_token"])

    source_warehouse = await client.post(
        "/v1/warehouses",
        headers=headers,
        json={"name": "Warehouse A", "location": "Almaty"},
    )
    destination_warehouse = await client.post(
        "/v1/warehouses",
        headers=headers,
        json={"name": "Warehouse B", "location": "Astana"},
    )
    assert source_warehouse.status_code == 201
    assert destination_warehouse.status_code == 201
    warehouses_page = await client.get("/v1/warehouses?limit=1", headers=headers)
    assert warehouses_page.status_code == 200
    assert warehouses_page.json()["has_more"] is True
    assert len(warehouses_page.json()["data"]) == 1

    product_response = await client.post(
        "/v1/products",
        headers=headers,
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
    assert product_response.status_code == 201
    variant_id = product_response.json()["variants"][0]["id"]
    source_warehouse_id = source_warehouse.json()["id"]
    destination_warehouse_id = destination_warehouse.json()["id"]

    seed_inventory = await client.post(
        "/v1/inventory/adjust",
        headers=headers,
        json={
            "variant_id": variant_id,
            "warehouse_id": source_warehouse_id,
            "quantity_delta": 10,
            "reason": "surplus",
            "note": "Initial stock",
        },
    )
    assert seed_inventory.status_code == 200
    assert seed_inventory.json()["quantity"] == 10

    first_transfer = await client.post(
        "/v1/transfers",
        headers=headers,
        json={
            "request_id": "txfr-001",
            "from_warehouse_id": source_warehouse_id,
            "to_warehouse_id": destination_warehouse_id,
            "variant_id": variant_id,
            "quantity": 6,
            "note": "Weekend restock",
        },
    )
    assert first_transfer.status_code == 201
    assert first_transfer.json()["status"] == "in_transit"
    over_received = await client.post(
        f"/v1/transfers/{first_transfer.json()['id']}/confirm",
        headers=headers,
        json={"received_quantity": 7},
    )
    assert over_received.status_code == 409
    assert over_received.json()["code"] == "TRANSFER_OVER_RECEIVED"

    second_transfer = await client.post(
        "/v1/transfers",
        headers=headers,
        json={
            "request_id": "txfr-002",
            "from_warehouse_id": source_warehouse_id,
            "to_warehouse_id": destination_warehouse_id,
            "variant_id": variant_id,
            "quantity": 5,
            "note": "Oversell attempt",
        },
    )
    assert second_transfer.status_code == 409
    assert second_transfer.json()["code"] == "INSUFFICIENT_STOCK"

    inventory_page = await client.get(
        f"/v1/inventory?warehouse_id={source_warehouse_id}",
        headers=headers,
    )
    assert inventory_page.status_code == 200
    source_row = inventory_page.json()["data"][0]
    assert source_row["quantity"] == 4

    transfers_page = await client.get("/v1/transfers", headers=headers)
    assert transfers_page.status_code == 200
    assert transfers_page.json()["total_count"] == 1


async def test_sku_and_transfer_request_id_are_tenant_scoped(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client)
    second_email = unique_email("second-owner")
    await bootstrap_tenant_admin(
        client,
        email=second_email,
        tenant_slug="second-shop",
    )

    first_tokens = await login_user(client, email="owner@arzanshop.kz", password="Secur3P@ss!")
    second_tokens = await login_user(client, email=second_email, password="Secur3P@ss!")
    first_headers = auth_headers(first_tokens["access_token"])
    second_headers = auth_headers(second_tokens["access_token"])

    shared_sku = "TENANT-SCOPED-SKU"
    first_source, first_destination, first_variant = await _seed_transfer_ready_stock(
        client,
        first_headers,
        sku=shared_sku,
    )
    second_source, second_destination, second_variant = await _seed_transfer_ready_stock(
        client,
        second_headers,
        sku=shared_sku,
    )

    for headers, source, destination, variant in (
        (first_headers, first_source, first_destination, first_variant),
        (second_headers, second_source, second_destination, second_variant),
    ):
        response = await client.post(
            "/v1/transfers",
            headers=headers,
            json={
                "request_id": "same-human-request-id",
                "from_warehouse_id": source,
                "to_warehouse_id": destination,
                "variant_id": variant,
                "quantity": 1,
                "note": "Same request id in different tenants is valid",
            },
        )
        assert response.status_code == 201, response.text
