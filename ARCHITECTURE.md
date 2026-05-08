# LeanStock Sprint 1 Architecture Notes

## Atomic inventory transfer

`POST /v1/transfers` locks the source `inventory_items` row with `SELECT FOR UPDATE`, checks available quantity inside the same database transaction, debits the source row, and inserts the transfer record before committing. That guarantees the critical LeanStock rule: source stock never goes negative because partial writes are impossible.

## Tenant isolation

LeanStock uses shared-schema row isolation. Every tenant-owned table contains `tenant_id`, and every service query includes that filter explicitly. The HTTP layer never accepts `tenant_id` in request bodies for normal tenant users; it comes from the signed JWT claims.

## Dead-stock decay

Dead-stock decay is implemented in application logic instead of PostgreSQL triggers. The rule set is controlled by:

- `DECAY_START_DAYS`
- `DECAY_INTERVAL_HOURS`
- `DECAY_DISCOUNT_PCT`

The daily Celery Beat job marks stale inventory as `liquidating`, then applies `max(current_price * discount_multiplier, liquidation_floor_price)` when the decay interval threshold is reached.

## Auth model

- Access token: short-lived JWT for API authorization.
- Refresh token: JWT with Redis-backed revocation record.
- Logout: deletes the Redis session for the refresh token.
- Rate limiting: per-IP Redis counters on register/login, capped at five attempts per minute.

