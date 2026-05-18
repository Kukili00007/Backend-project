from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import auth_headers, bootstrap_tenant_admin, latest_email_job, login_user


async def _seed_catalog(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str, str]:
    warehouse = await client.post(
        "/v1/warehouses",
        headers=headers,
        json={"name": "Main Warehouse", "location": "Almaty"},
    )
    assert warehouse.status_code == 201, warehouse.text

    product = await client.post(
        "/v1/products",
        headers=headers,
        json={
            "name": "Classic T-Shirt",
            "category": "Clothing",
            "unit_of_measure": "pcs",
            "variants": [
                {
                    "sku": "TSHIRT-RED-L-PROC",
                    "color": "Red",
                    "size": "L",
                    "cost_price": 2100.0,
                    "selling_price": 4990.0,
                    "liquidation_floor_price": 2990.0,
                }
            ],
        },
    )
    assert product.status_code == 201, product.text
    return warehouse.json()["id"], product.json()["id"], product.json()["variants"][0]["id"]


async def test_supplier_purchase_order_flow_receives_inventory(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client)
    tokens = await login_user(client, email="owner@arzanshop.kz", password="Secur3P@ss!")
    headers = auth_headers(tokens["access_token"])
    warehouse_id, product_id, variant_id = await _seed_catalog(client, headers)

    update_product = await client.patch(
        f"/v1/products/{product_id}",
        headers=headers,
        json={"category": "Apparel"},
    )
    assert update_product.status_code == 200
    assert update_product.json()["category"] == "Apparel"

    update_variant = await client.patch(
        f"/v1/products/variants/{variant_id}",
        headers=headers,
        json={"selling_price": 4790.0, "liquidation_floor_price": 2990.0},
    )
    assert update_variant.status_code == 200
    assert update_variant.json()["selling_price"] == "4790.00"

    supplier = await client.post(
        "/v1/suppliers",
        headers=headers,
        json={
            "name": "Almaty Textile Supply",
            "contact_email": "orders@supplier.kz",
            "phone": "+77001234567",
            "lead_time_days": 5,
        },
    )
    assert supplier.status_code == 201, supplier.text

    update_supplier = await client.patch(
        f"/v1/suppliers/{supplier.json()['id']}",
        headers=headers,
        json={"lead_time_days": 6},
    )
    assert update_supplier.status_code == 200
    assert update_supplier.json()["lead_time_days"] == 6

    purchase_order = await client.post(
        "/v1/purchase-orders",
        headers=headers,
        json={
            "po_number": "PO-TEST-001",
            "supplier_id": supplier.json()["id"],
            "warehouse_id": warehouse_id,
            "variant_id": variant_id,
            "quantity": 5,
            "expected_unit_cost": 2200.0,
        },
    )
    assert purchase_order.status_code == 201, purchase_order.text
    assert purchase_order.json()["status"] == "draft"

    submitted = await client.post(
        f"/v1/purchase-orders/{purchase_order.json()['id']}/submit",
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    po_email = await latest_email_job("orders@supplier.kz", "purchase_order_confirmation")
    assert po_email.subject == "LeanStock purchase order PO-TEST-001"

    confirmed = await client.post(
        f"/v1/purchase-orders/{purchase_order.json()['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    over_received = await client.post(
        f"/v1/purchase-orders/{purchase_order.json()['id']}/receive",
        headers=headers,
        json={"received_quantity": 6},
    )
    assert over_received.status_code == 409
    assert over_received.json()["code"] == "PURCHASE_ORDER_OVER_RECEIVED"

    received = await client.post(
        f"/v1/purchase-orders/{purchase_order.json()['id']}/receive",
        headers=headers,
        json={"received_quantity": 5},
    )
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "received"

    inventory = await client.get(f"/v1/inventory?warehouse_id={warehouse_id}", headers=headers)
    assert inventory.status_code == 200
    assert inventory.json()["data"][0]["quantity"] == 5


async def test_low_stock_alert_and_forecast_endpoint(client: AsyncClient) -> None:
    await bootstrap_tenant_admin(client)
    tokens = await login_user(client, email="owner@arzanshop.kz", password="Secur3P@ss!")
    headers = auth_headers(tokens["access_token"])
    warehouse_id, _, variant_id = await _seed_catalog(client, headers)

    seed_stock = await client.post(
        "/v1/inventory/adjust",
        headers=headers,
        json={
            "variant_id": variant_id,
            "warehouse_id": warehouse_id,
            "quantity_delta": 10,
            "reason": "surplus",
            "note": "Initial stock",
        },
    )
    assert seed_stock.status_code == 200

    reduce_stock = await client.post(
        "/v1/inventory/adjust",
        headers=headers,
        json={
            "variant_id": variant_id,
            "warehouse_id": warehouse_id,
            "quantity_delta": -7,
            "reason": "count_correction",
            "note": "Demand signal for forecast",
        },
    )
    assert reduce_stock.status_code == 200
    assert reduce_stock.json()["quantity"] == 3
    await latest_email_job("owner@arzanshop.kz", "low_stock_alert")

    forecast = await client.get(
        f"/v1/inventory/forecast?warehouse_id={warehouse_id}&reorder_only=true",
        headers=headers,
    )
    assert forecast.status_code == 200, forecast.text
    suggestion = forecast.json()["data"][0]
    assert suggestion["sku"] == "TSHIRT-RED-L-PROC"
    assert suggestion["observed_outgoing_units"] == 7
    assert suggestion["recommended_reorder_quantity"] > 0
    assert suggestion["urgency"] == "reorder_now"
