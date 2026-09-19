# GST Pro — GST Invoice & Tax Compliance Platform

A production-oriented Indian GST invoicing and compliance platform foundation. The application is designed around a multi-company / multi-GSTIN model and separates GST calculation, compliance rules, return drafting and external IRP/GSP integration.

## Current v1.2 capabilities
- Multi-company / multi-GSTIN domain model
- Owner / Accountant / CA / Viewer RBAC
- JWT authentication and PBKDF2 password hashing
- Customer, vendor and product/service masters
- Tax Invoice, Bill of Supply, Credit Note and Debit Note workflow foundation
- Regular and Composition scheme logic
- Intra-state CGST+SGST / inter-state IGST calculation
- GST rate presets with one-click recalculation
- Catalog line items + explicit Custom Entry
- GSTIN/state validation and AATO-driven HSN validation
- Mock GST INV-01 payload + deterministic mock IRN + cancellation flow
- Provider boundary for licensed GSP/IRP integration
- Maker-checker invoice approval before e-invoice generation
- Hash-chained audit log + integrity verification endpoint
- GSTR-1 draft: B2B, B2C, CDNR and HSN summary with GSTN-oriented payload envelope
- GSTR-3B draft: outward supplies, ITC and net tax tables
- Purchase register + GSTR-2B reconciliation
- Return-period locks
- PDF invoice and CSV/Excel exports
- PostgreSQL schema, migrations/extensions and Docker Compose
- Responsive web UI with login, dashboard, invoicing, masters, returns and reconciliation

## Demo accounts
- Owner/maker: `admin@gstpro.local` / `admin`
- CA/approver: `ca@gstpro.local` / `caadmin123`

Change these credentials and set a strong `JWT_SECRET` before any real deployment.

## Run with Docker
```bash
docker compose up --build
```
Web: `http://localhost:3000`  API: `http://localhost:8000`

## Local development
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install
npm run dev
```

## Demo flow
1. Sign in as Owner.
2. Create/save an invoice.
3. Submit it for approval.
4. Sign out and sign in as the Demo CA.
5. Approve the invoice.
6. Return to Owner and generate the mock IRN.
7. Open Returns and generate the GSTR-1/GSTR-3B drafts.
8. Use Reconciliation for purchase vs GSTR-2B checks.

## Compliance notes
The application keeps thresholds and compliance rules separate from the UI. For this build, e-invoicing is configured at the ₹5 crore AATO threshold and the 30-day reporting control is applied to AATO ₹10 crore+ from 1 April 2025. HSN reporting is configured as 4 digits up to ₹5 crore AATO and 6 digits above ₹5 crore for relevant GSTR-1 reporting. Production filing must always be validated against the current GSTN/IRP schema, notifications, exemptions and taxpayer category.

## Live IRP/GSP integration
`backend/app/einvoice.py` defines the provider contract. `MockIRPProvider` is used for development. `GSPIRPProvider` is the boundary for a licensed GSP/IRP implementation. A live connector should add credential/token lifecycle, request signing/encryption where required, idempotency, retry/backoff, status polling, error mapping, cancellation handling and secure secret storage.

## Production checklist before live filing
- Use PostgreSQL as the operational source of truth and move critical writes to SQL transactions.
- Use a production secret manager, strong JWT secret, refresh-token rotation and MFA.
- Encrypt PAN/GSTIN/bank details where required by the deployment threat model and regulatory policy.
- Complete every GSTN offline/JSON return table and validate against the current portal version.
- Add official GSP/IRP certification/credentials and sandbox-to-production configuration.
- Add backup/restore, observability, rate limiting, WAF/API gateway and disaster recovery.
- Complete current GSTIN/HSN master synchronization and exemption/category rules.

## Verification
Backend automated tests currently cover GST calculation, locked periods, GSTR-2B reconciliation, maker-checker controls and audit-chain integrity.
