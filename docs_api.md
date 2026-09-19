# GST Pro API v1.1

## Core
- `GET /health`
- `GET /api/config`
- `GET /api/gst-rate-presets`
- `GET /api/companies`
- `GET /api/gstins?company_id=...`

## Masters
- `GET/POST /api/customers`
- `GET/POST /api/vendors`
- `GET/POST /api/products`
- `GET /api/validate-gstin/{gstin}`

## Invoices
- `POST /api/invoices/calculate`
- `POST /api/invoices`
- `GET /api/invoices`
- `GET /api/invoices/{id}`
- `DELETE /api/invoices/{id}` (soft-cancel)
- `GET /api/invoices/{id}/pdf`

Invoice creation is blocked when its GSTIN's return period has been locked.

## E-invoice
- `POST /api/einvoice/mock`
- `GET /api/einvoice/{id}/json`
- `POST /api/einvoice/{id}/cancel`

The mock IRP enforces the configurable 30-day reporting rule for AATO >= ₹10 crore and the 24-hour IRN cancellation window.

## Returns
- `GET /api/returns/gstr1/draft?period=YYYY-MM`
- `GET /api/returns/gstr3b/draft?period=YYYY-MM`
- `POST /api/returns/lock`
- `GET /api/returns`
- `GET /api/export/gstr1.csv`
- `GET /api/export/invoices.xlsx`

## Purchases / GSTR-2B
- `POST /api/purchases`
- `GET /api/purchases`
- `POST /api/gstr2b/import`
- `GET /api/gstr2b?period=YYYY-MM`
- `GET /api/reconciliation?period=YYYY-MM`

The reconciliation engine currently matches vendor GSTIN + supplier invoice number and then checks invoice total. Production matching should additionally use document date, tax components, amendment flags and portal status.

## Authentication
`POST /api/auth/login` returns a short-lived JWT. Demo credentials are documented in README. Production deployment must enforce bearer authentication on all protected endpoints, use refresh tokens/MFA, rotate secrets, and replace demo passwords with strong password hashes.
