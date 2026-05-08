# LeanStock Backend

LeanStock is a multi-tenant inventory backend built with FastAPI, SQLModel/SQLAlchemy async, PostgreSQL 15, Redis, Celery worker + beat, Alembic migrations, JWT auth, and Argon2 password hashing.

The final pre-defense version keeps the original Sprint 1 transfer flow and adds application-level email verification, password reset, Gmail API delivery through Google OAuth2, refresh-token rotation, admin email queue visibility, and manual decay triggering.

## What Is Implemented

- JWT access/refresh auth with Argon2 password hashing.
- Email verification on signup: users start unverified, receive an email job, then verify through `POST /v1/auth/verify-email`.
- Password reset through queued email: `POST /v1/auth/password-reset/request` and `POST /v1/auth/password-reset/confirm`.
- Refresh token rotation: every refresh revokes the old refresh `jti` in Redis and issues a new refresh token.
- Logout revokes the submitted refresh token.
- RBAC roles: `super_admin`, `tenant_admin`, `warehouse_manager`, `analyst`.
- Unverified users can login, but protected business routes return `403 EMAIL_NOT_VERIFIED`.
- Shared-schema multi-tenancy with tenant filters on warehouse, product, inventory, transfer, and admin queue reads.
- Atomic stock transfer using PostgreSQL row locks.
- Async email queue with `email_jobs` status: `queued`, `sent`, `failed`, plus `retry_count` and `error_message`.
- Gmail API email sender authorized by Google OAuth2 refresh token.
- Email notifications for verification, password reset, transfer created, and transfer completed.
- Admin queue endpoint: `GET /v1/admin/email-jobs`.
- Manual decay endpoint: `POST /v1/admin/decay/run`.
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
- application source code under `app/`
- Postman files under `postman/`

Run migrations manually if needed:

```bash
docker compose run --rm migrate alembic upgrade head
```

## Environment

Docker Compose reads `.env.example` by default. For a real defense run, copy it to `.env` or edit the compose env file values with real secrets.

Required core values:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | JWT signing secret, at least 32 chars |
| `DATABASE_URL` | Async PostgreSQL URL |
| `REDIS_URL` | Redis for rate limits, refresh tokens, reservations, Celery broker |
| `CELERY_BROKER_URL` | Celery broker, defaults to Redis |
| `CELERY_RESULT_BACKEND` | Celery result backend, defaults to Redis |

Email values:

| Variable | Purpose |
| --- | --- |
| `EMAIL_PROVIDER=gmail_oauth2` | Selects Gmail OAuth2 sender |
| `EMAIL_ENABLED=true` | Enables real Gmail API sending in the worker |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | Long-lived refresh token for Gmail API access |
| `GOOGLE_OAUTH_TOKEN_URI` | Usually `https://oauth2.googleapis.com/token` |
| `GMAIL_SENDER_EMAIL` | Gmail address used in the `From` header |
| `FRONTEND_BASE_URL` | Used to build verification/reset links |
| `API_BASE_URL` | Fallback base URL for links |

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
21. Manager Create Product 403
22. List Products
23. Get Product
24. Adjust Inventory
25. List Inventory
26. Reserve Inventory
27. Create Transfer
28. List Transfers
29. Confirm Transfer
30. Create Transfer For Cancel
31. Cancel Transfer
32. List Email Jobs
33. Trigger Decay Run

The collection also keeps every implemented endpoint as a separate request so the examiner can randomly pick tabs during oral defense.

## Local Quality Checks

If dependencies are installed locally:

```bash
ruff check app tests migrations
pytest
```

Or run inside Docker:

```bash
docker compose up --build -d postgres redis
docker compose build api
docker compose run --rm api pytest
```

## Architecture Notes

- Business data is tenant-scoped by `current_user.tenant_id`.
- RBAC is enforced in router dependencies; wrong roles return `403`, missing or invalid tokens return `401`.
- Unverified users are blocked in RBAC-protected business/admin routes.
- Transfer creation debits source inventory in the same transaction with row locking.
- Transfer confirmation credits destination inventory and writes audit logs.
- Refresh token state is stored in Redis by `jti`; rotation deletes the old `jti`.
- Email token tables store SHA-256 token hashes, not raw tokens.
- Email job rows are durable and visible to tenant admins through `/v1/admin/email-jobs`.
- Celery beat runs scheduled dead-stock decay; admins can trigger the same decay logic for their tenant through `/v1/admin/decay/run`.
