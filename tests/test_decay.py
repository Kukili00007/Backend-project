from __future__ import annotations

from decimal import Decimal

from app.services.decay_service import calculate_decay_price


def test_calculate_decay_price_respects_percentage() -> None:
    assert calculate_decay_price(Decimal("5000"), Decimal("3000"), Decimal("10")) == Decimal("4500.00")


def test_calculate_decay_price_respects_floor() -> None:
    assert calculate_decay_price(Decimal("3100"), Decimal("3000"), Decimal("10")) == Decimal("3000")
