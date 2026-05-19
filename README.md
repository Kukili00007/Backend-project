# LeanStock Backend

LeanStock is a multi-tenant inventory full-stack demo built with FastAPI, SQLModel/SQLAlchemy async, PostgreSQL 15, Redis, Celery worker + beat, Alembic migrations, JWT auth, Argon2 password hashing, and a containerized browser frontend under `frontend/`.

The final pre-defense version keeps the original Sprint 1 transfer flow and adds application-level email verification, password reset, Gmail API delivery through Google OAuth2, refresh-token rotation, admin email queue visibility, and manual decay triggering.

## What Is Implemented

- JWT access/refresh auth with Argon2 password hashing.
- Email verification on signup: users start unverified, receive an email job, then verify through `POST /v1/auth/verify-email`.
- Password reset through queued email: `POST /v1/auth/password-reset/request` and `POST /v1/auth/password-reset/confirm`.
- Refresh token rotation: every refresh revokes the old refresh `jti` in Redis and issues a new refresh token.
- Logout revokes the submitted refresh token.
- RBAC roles: `super_admin`, `tenant_admin`, `warehouse_manager`, `analyst`.
- First-user bootstrap can create either a tenant admin or a super admin; later `super_admin` creation requires an existing verified super admin.
- Unverified users can login, but protected business routes return `403 EMAIL_NOT_VERIFIED`.
- Shared-schema multi-tenancy with tenant filters on warehouse, product, inventory, transfer, procurement, and admin queue reads.
- Tenant-scoped business keys: SKU values and transfer `request_id` values can repeat safely across different tenants.
- Functional frontend demo for auth, RBAC, catalog, inventory, transfers, suppliers, purchase orders, forecasting, decay, and email jobs.
- Product and warehouse CRUD with soft deactivation.
- Atomic stock transfer using PostgreSQL row locks.
- Supplier CRUD and purchase order workflow: draft -> submitted -> confirmed -> received/cancelled.
- Purchase order receiving credits inventory in one transaction with row locks.
- Forecasting endpoint: `GET /v1/inventory/forecast` returns moving-average reorder suggestions from audit history.
- Async email queue with `email_jobs` status: `queued`, `sent`, `failed`, plus `retry_count` and `error_message`.
- Gmail API email sender authorized by Google OAuth2 refresh token.
- Email notifications for verification, password reset, low-stock alerts, purchase order confirmations, transfer receipts, and dead-stock decay summary alerts.
- Admin queue endpoint: `GET /v1/admin/email-jobs`.
- Manual decay endpoint: `POST /v1/admin/decay/run`.
- Cursor pagination on all list endpoints, including warehouses.
- Standard error responses documented in `openapi.yaml` for `400`, `401`, `403`, `404`, `409`, `422`, `429`, and `500`.
- Swagger UI at `/docs` and Postman collection in `postman/`.

## Important Defense Explanation

Google OAuth2 is used only to authorize the backend to send email through the Gmail API.

Application login is still the project's own JWT system:

- Users register and login with LeanStock credentials.
- Passwords are hashed with Argon2.
- Access/refresh tokens are LeanStock JWTs.
- Email verification and password reset tokens are LeanStock application tokens.
- Google Sign-In is not used and does not replace JWT auth.

## Quick Start With Docker Compose

```bash
docker compose up --build -d
docker compose logs -f api
```

Open:

- Frontend: [http://localhost:3000](http://localhost:3000)
- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health: [http://localhost:8000/health](http://localhost:8000/health)

## Submission

The pre-defense submission must be a GitHub repository link. A ZIP-only submission is not accepted by the grading requirements.

The repository should include:

- `.env.example`
- `README.md`
- `openapi.yaml`
- `migrations/`
- `tests/`
- `frontend/`
- `CHECKLIST.txt`
- `DEPLOYED_URL.txt`
- `VIDEO_LINK.txt`
- application source code under `app/`
- Postman files under `postman/`

Run migrations manually if needed:

```bash
docker compose run --rm migrate alembic upgrade head
```

## Environment

Docker Compose reads `.env.example` first and then overlays `.env` if it exists. For a real defense run, copy `.env.example` to `.env` and put real secrets only in `.env`.

Required core values:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` / `JWT_SECRET_KEY` | JWT access-token signing secret, at least 32 chars |
| `JWT_REFRESH_SECRET_KEY` | Separate JWT refresh-token signing secret |
| `DATABASE_URL` | Async PostgreSQL URL |
| `REDIS_URL` | Redis for rate limits, refresh tokens, reservations, Celery broker |
| `CELERY_BROKER_URL` | Celery broker, defaults to Redis |
| `CELERY_RESULT_BACKEND` | Celery result backend, defaults to Redis |
| `BACKEND_PORT` | Local exposed backend port, defaults to 8000 |
| `FRONTEND_PORT` | Local exposed frontend port, defaults to 3000 |
| `APP_ENV` / `ENVIRONMENT` | `development`, `test`, or `production`; production validates real secrets and CORS |
| `CORS_ORIGINS` | Comma-separated frontend origins allowed by the backend |

Email values:

| Variable | Purpose |
| --- | --- |
| `EMAIL_PROVIDER=gmail_oauth2` | Selects Gmail OAuth2 sender |
| `EMAIL_ENABLED=true` | Enables real Gmail API sending in the worker |
| `EMAIL_API_KEY` / `SENDGRID_API_KEY` | Kept in `.env.example` for assignment compatibility; Gmail OAuth2 deployments can leave it unused |
| `EMAIL_FROM_ADDRESS` / `FROM_EMAIL` | Fallback sender address |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | Long-lived refresh token for Gmail API access |
| `GOOGLE_OAUTH_TOKEN_URI` | Usually `https://oauth2.googleapis.com/token` |
| `GMAIL_SENDER_EMAIL` | Gmail address used in the `From` header |
| `FRONTEND_BASE_URL` | Used to build verification/reset links |
| `API_BASE_URL` | Fallback base URL for links |

DeployRocks note: use Docker service names inside URLs, for example `postgres` and `redis`, not `localhost`. Set `FRONTEND_BASE_URL` and `CORS_ORIGINS` to the deployed frontend URL after DeployRocks creates the domain.

## Gmail OAuth2 Setup

1. In Google Cloud Console, create or choose a project.
2. Enable the Gmail API.
3. Configure OAuth consent screen.
4. Create an OAuth 2.0 Client ID. For local token generation, a Desktop app client is simplest.
5. Request the Gmail send scope:

```text
https://www.googleapis.com/auth/gmail.send
```

6. Get an authorization code from Google's OAuth consent flow.
7. Exchange the authorization code for tokens:

```bash
curl -X POST https://oauth2.googleapis.com/token \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "code=AUTHORIZATION_CODE" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=YOUR_REDIRECT_URI"
```

8. Put the returned `refresh_token` into `GOOGLE_OAUTH_REFRESH_TOKEN`.

The Celery worker exchanges this refresh token for short-lived access tokens and calls `users.messages.send` on the Gmail API. API endpoints only create database jobs and enqueue Celery tasks; they do not wait for Gmail.

## Postman Demo Order

Import:

- `postman/LeanStock.postman_collection.json`
- `postman/LeanStock.postman_environment.json`

Run in this order:

1. Health Check
2. Register Tenant Admin
3. Copy verification token from the received email into `verificationToken`
4. Verify Email
5. Resend Verification
6. Login Tenant Admin
7. Refresh Token
8. Logout
9. Password Reset Request
10. Copy reset token from the received email into `passwordResetToken`
11. Password Reset Confirm
12. Login After Password Reset
13. Register Warehouse Manager
14. Copy manager verification token into `managerVerificationToken`
15. Verify Manager Email
16. Login Warehouse Manager
17. Create Warehouse A
18. Create Warehouse B
19. List Warehouses
20. Create Product
21. Update Product / Variant
22. Manager Create Product 403
23. List Products
24. Get Product
25. Adjust Inventory
26. List Inventory
27. Reserve Inventory
28. Forecast Reorder Suggestions
29. Create Transfer
30. List Transfers
31. Confirm Transfer
32. Create Transfer For Cancel
33. Cancel Transfer
34. Create Supplier
35. Create / Submit / Confirm / Receive Purchase Order
36. List Email Jobs
37. Trigger Decay Run

The collection also keeps every implemented endpoint as a separate request so the examiner can randomly pick tabs during oral defense.

## Local Quality Checks

If dependencies are installed locally:

```bash
ruff check app tests migrations
pytest
```

The Docker test service uses an isolated `postgres-test` database from `docker-compose.test.yml`, so running tests will not wipe the demo database used by the API:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test
```

## DeployRocks Deployment

1. Push this repository to GitHub.
2. Open `https://dashboard.deployrocks.com`, connect the repository, and select Docker Compose deployment.
3. Configure production environment variables from `.env.example`; replace all secrets and Gmail OAuth values.
4. Set `APP_ENV=production`, `ENVIRONMENT=production`, `EMAIL_ENABLED=true`, and production `CORS_ORIGINS`.
5. Use service hostnames in URLs: `postgres` for PostgreSQL and `redis` for Redis.
6. The API container runs `alembic upgrade head` on startup. `worker` and `beat` are selected with `SERVICE_ROLE` and expose a lightweight health port for Dokku checks.
7. After deployment, open the generated frontend URL, test `/docs` for the backend URL, and put the final frontend domain into `DEPLOYED_URL.txt`.

## Frontend Demo

The frontend is a lightweight browser demo in `frontend/`. It does not mock data. It stores JWTs in browser local storage for the defense demo and calls the configured backend API directly.

Main demo flows:

- Register -> real email verification -> login -> protected pages.
- Product and warehouse CRUD.
- Inventory adjust, reserve, low-stock alert, and forecasting.
- Atomic transfer create/confirm/cancel.
- Supplier and purchase order create/submit/confirm/receive.
- Admin email job visibility and manual decay trigger.

## Architecture Notes

- Business data is tenant-scoped by `current_user.tenant_id`.
- Product SKUs and transfer idempotency keys are tenant-scoped, so one tenant cannot block another tenant's SKU or transfer request naming.
- RBAC is enforced in router dependencies; wrong roles return `403`, missing or invalid tokens return `401`.
- Unverified users are blocked in RBAC-protected business/admin routes.
- Transfer creation debits source inventory in the same transaction with row locking.
- Transfer confirmation credits destination inventory and writes audit logs.
- Purchase order receiving credits inventory in the same transaction with row locking.
- Dead-stock decay locks inventory rows with `FOR UPDATE SKIP LOCKED` so overlapping worker/admin runs do not double-discount the same row.
- Forecasting uses audit-log outgoing movement history to calculate average daily demand and reorder recommendations.
- Refresh token state is stored in Redis by `jti`; rotation deletes the old `jti`.
- The FastAPI lifespan opens/closes Redis and disposes the SQLAlchemy engine on shutdown.
- Email token tables store SHA-256 token hashes, not raw tokens.
- Email job rows are durable and visible to tenant admins through `/v1/admin/email-jobs`.
- Celery beat runs scheduled dead-stock decay; admins can trigger the same decay logic for their tenant through `/v1/admin/decay/run`.
