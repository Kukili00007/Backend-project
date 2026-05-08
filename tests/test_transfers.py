from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import auth_headers, bootstrap_tenant_admin, login_user


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

