# GST Pro — Web App Deployment (Level 8)

## Goal

Run GST Pro as a browser-accessible web application from the GitHub repository:

```
Browser
  ↓ HTTPS
Render Web — Next.js frontend
  ↓ HTTPS
Render Web — FastAPI backend
  ↓ TLS
Supabase Postgres
```

The GitHub repository remains the source of truth. A push to the selected deployment branch can trigger a new build/deploy on Render.

## Zero-cost prototype stack

For a development/demo deployment, the current practical no-cost architecture is:

- **GitHub** — source control.
- **Render Free Web Service** — Next.js frontend.
- **Render Free Web Service** — FastAPI backend.
- **Supabase Free Postgres** — persistent PostgreSQL database.
- **Render/Supabase generated HTTPS URLs** — no custom domain required.
- **Mock e-invoice provider** — no paid GST API dependency while the workflow is being validated.

This is a **free prototype/demo environment, not a production SLA**. Render free web services spin down after 15 minutes of inactivity and can take about a minute to wake. Supabase Free projects may pause after a week of low activity. Supabase Free currently provides 500 MB database storage per project.

## Render setup

The repository contains `render.yaml` for the two web services.

### 1. Create the database

Create a Supabase Free Postgres project and obtain its PostgreSQL connection string.

Set:

```
DATABASE_URL=postgresql+psycopg://...
```

Run the repository's PostgreSQL schema/migrations against that database before first production-mode login.

### 2. Create the Render Blueprint

In Render, create a Blueprint from this GitHub repository and use:

```
render.yaml
```

The Blueprint creates:

- `gstpro-api`
- `gstpro-web`

Both use the repository Dockerfiles.

### 3. Configure API secrets

Set these on `gstpro-api`:

```
GSTPRO_MODE=production
ENVIRONMENT=production
DATABASE_URL=<Supabase PostgreSQL URL>
JWT_SECRET=<long random secret>
CORS_ALLOWED_ORIGINS=https://<actual-gstpro-web>.onrender.com
MOCK_EINVOICE=true
```

Never commit real secrets.

### 4. Configure frontend API URL

Set on `gstpro-web`:

```
NEXT_PUBLIC_API_URL=https://<actual-gstpro-api>.onrender.com
PORT=10000
HOSTNAME=0.0.0.0
```

Because `NEXT_PUBLIC_API_URL` is consumed by the Next.js browser bundle, it must be present during the frontend build/deploy.

## What makes it a real web app?

The browser URL alone is not enough.

GST Pro needs all of these:

1. Public HTTPS frontend.
2. Public HTTPS API endpoint.
3. Persistent PostgreSQL database.
4. Production JWT secret.
5. Correct CORS allow-list.
6. Environment-specific configuration.
7. Database schema/migrations applied to the hosted database.
8. Health/readiness endpoint.
9. Error logging/monitoring.
10. Backups and recovery process before real business data is used.
11. Secure secret storage.
12. A real domain is optional; the Render HTTPS domain works without buying a domain.

## Government GST integrations

GST Pro currently has a provider boundary and a mock IRP provider. That is intentional.

Do **not** assume there is a permanently free public API that can legally/operationally replace the GSTN/GSP onboarding process for production e-invoice or e-way-bill transactions.

For live e-invoice integration, use the official sandbox/onboarding process and an authorized integration route (direct taxpayer integration where eligible or a GSP). For e-way bill API access, the official documentation describes onboarding, credentials, HTTPS/static-IP requirements and pre-production testing.

Therefore Level 8 should keep:

```
GST Pro
  → provider interface
     → Mock provider (development)
     → Licensed/approved GSP or eligible direct API integration (production)
```

No paid external GST API is required to validate the application's internal invoice, approval, returns-draft and reconciliation workflows.

## Production upgrade path

When GST Pro moves from demo to real business use, replace the free prototype stack with:

- Paid/always-on application hosting.
- Paid database tier with backups.
- Strong secret manager.
- Custom domain + DNS.
- Monitoring/alerting.
- SMTP/transactional email if notifications are enabled.
- Real GSP/IRP credentials and sandbox-to-production approval.
- E-way bill API integration if required.
- GSTN/current schema and compliance-rule verification.
- Backup/restore and disaster-recovery testing.

