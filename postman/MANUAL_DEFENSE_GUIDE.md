# LeanStock Postman Manual Defense Guide

Use this guide when the examiner asks you to demonstrate the backend without Postman automation.

## Rule

Do not run the whole collection. Open requests one by one and manually copy values from each response into the next request or into the Postman environment.

## Environment Values To Fill By Hand

- `baseUrl`: `http://localhost:8000`
- `accessToken`: copy from login or refresh response
- `tenantAdminAccessToken`: copy the tenant admin access token if you want to switch back after manager login
- `managerAccessToken`: copy from manager login response
- `refreshToken`: copy from login or refresh response
- `verificationToken`: copy from the real verification email
- `managerVerificationToken`: copy from the manager verification email
- `passwordResetToken`: copy from the real password reset email
- `sourceWarehouseId`: copy Warehouse A `id`
- `destinationWarehouseId`: copy Warehouse B `id`
- `productId`: copy product `id`
- `variantId`: copy first variant `id`
- `transferId`: copy transfer `id`
- `cancelTransferId`: copy cancel-flow transfer `id`
- `supplierId`: copy supplier `id`
- `purchaseOrderId`: copy purchase order `id`

## Demo Order

1. Health Check
2. Register Tenant Admin
3. Copy verification token from the real email
4. Verify Email
5. Login Tenant Admin
6. Copy `access_token` and `refresh_token`
7. Refresh Token and copy the new tokens
8. Create Warehouse A and copy its `id`
9. Create Warehouse B and copy its `id`
10. List Warehouses
11. Create Product and copy `productId` plus `variantId`
12. Adjust Inventory
13. Reserve Inventory
14. Forecast Reorder Suggestions
15. Create Transfer and copy `transferId`
16. Confirm Transfer
17. Create Transfer For Cancel and copy `cancelTransferId`
18. Cancel Transfer
19. Create Supplier and copy `supplierId`
20. Create Purchase Order and copy `purchaseOrderId`
21. Submit Purchase Order
22. Confirm Purchase Order
23. Receive Purchase Order
24. Register Warehouse Manager
25. Copy manager verification token from email
26. Verify Manager Email
27. Login Warehouse Manager and copy `managerAccessToken`
28. Run Manager Create Product 403 with manager token
29. Switch back to tenant admin token
30. List Email Jobs
31. Trigger Decay Run

## What To Say

- Auth uses LeanStock JWT access and refresh tokens.
- Refresh rotates the refresh token and revokes the old `jti` in Redis.
- Email verification/password reset tokens are sent by email and stored hashed in the database.
- Protected business endpoints require a verified user and correct role.
- Inventory and transfer operations use database transactions and row locks to prevent overselling.
- Purchase order receiving uses the same row-lock pattern to credit inventory atomically.
- Forecasting uses audit-log movement history to produce reorder suggestions.
- Email delivery is queued in `email_jobs`; Celery worker sends it asynchronously.
- Dead-stock decay is a background job run by Celery beat, and `/v1/admin/decay/run` triggers it manually for demo.
