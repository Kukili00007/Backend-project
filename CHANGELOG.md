# CHANGELOG

## Final defense full-stack completion

- Added a containerized `frontend/` demo that consumes the real backend API.
- Added product/warehouse update and soft-delete endpoints.
- Added supplier CRUD and purchase order workflow endpoints.
- Added purchase order receiving with inventory row locking.
- Added reorder forecasting endpoint based on audit-log movement history.
- Added low-stock and purchase-order email job enqueueing.
- Added final submission files: `CHECKLIST.txt`, `DEPLOYED_URL.txt`, and `VIDEO_LINK.txt`.
- Regenerated `openapi.yaml` from the live FastAPI application.
- Added migration `004_tenant_scoped_business_keys` so product SKUs and transfer `request_id` values are isolated per tenant.
- Removed raw SQL text expressions from Alembic migrations; migrations now use SQLAlchemy constructs for defaults and index predicates.
- Added row locks to dead-stock decay selection so parallel scheduled/manual runs skip rows already being processed.
- Added SQLAlchemy engine disposal in the FastAPI lifespan shutdown path.

## Final pre-defense implementation

- Added application-level email verification on signup while keeping LeanStock JWT auth as the login system. Google OAuth2 is used only to authorize Gmail API email sending.
- Added password reset request/confirm endpoints with hashed reset tokens and Argon2 password updates.
- Added refresh-token rotation: old refresh `jti` values are removed from Redis and new refresh tokens are issued on every refresh.
- Added durable `email_jobs` queue visibility with status, retry count, error message, created timestamp, and sent timestamp.
- Added Celery email task and Gmail API sender using OAuth2 refresh tokens. API routes create email jobs and enqueue work instead of waiting on Gmail.
- Added transfer-created and transfer-completed business notification emails.
- Added `/v1/admin/email-jobs` and `/v1/admin/decay/run`.
- Regenerated `openapi.yaml` from the implemented FastAPI routes.
- Expanded the Postman collection into a flat final-defense collection with every implemented endpoint as a separate request.
- Added tests for password strength, email verification token flow, password reset token flow, refresh rotation, unverified-user blocking, RBAC 403, decay formula, and insufficient-stock transfer behavior.

## Sprint 1 implementation alignment

- The original blueprint listed analytics, alerts, and super-admin tenant management. Those endpoints are intentionally not implemented in this milestone so the repository stays focused on the assignment's required first slice: auth/RBAC, multi-tenant catalog, inventory, transfers, and decay automation.
- `POST /auth/register` was extended beyond the earlier draft so the first tenant admin and tenant can be created without a seed script. This keeps the project runnable by a stranger with only `docker compose up`.
- Product creation accepts the initial variant matrix inline inside `POST /products` instead of using a separate variant-creation endpoint. That reduces setup friction for the defense flow while preserving the same underlying product/variant schema.
- Transfer confirmation is tenant-scoped rather than warehouse-assignment-scoped because the approved schema has no user-to-warehouse mapping table. The authorization layer still enforces role-based access with correct `403 Forbidden` responses.
- Swagger now reflects the implemented sprint-1 surface area rather than the full future roadmap.
