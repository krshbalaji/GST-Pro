CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS companies (
  id uuid primary key, legal_name text not null, trade_name text, pan varchar(10) not null,
  aato numeric(18,2) not null default 0, address jsonb, created_at timestamptz default now(), updated_at timestamptz default now()
);
CREATE TABLE IF NOT EXISTS gstins (
  id uuid primary key, company_id uuid not null references companies(id), gstin varchar(15) not null unique,
  state_code varchar(2) not null, scheme varchar(20) not null, legal_name text, trade_name text, address jsonb,
  is_active boolean default true, created_at timestamptz default now(), updated_at timestamptz default now()
);
CREATE TABLE IF NOT EXISTS users (
  id uuid primary key, company_id uuid references companies(id), name text, email text unique, role varchar(20) not null,
  password_hash text not null, is_active boolean default true, last_login_at timestamptz, created_at timestamptz default now(), updated_at timestamptz default now()
);
CREATE TABLE IF NOT EXISTS customers (
  id uuid primary key, company_id uuid references companies(id), name text not null, gstin varchar(15), state_code varchar(2), address jsonb, pan varchar(10), is_active boolean default true, created_at timestamptz default now(), updated_at timestamptz default now()
);
CREATE TABLE IF NOT EXISTS vendors (
  id uuid primary key, company_id uuid references companies(id), name text not null, gstin varchar(15), state_code varchar(2), address jsonb, pan varchar(10), is_active boolean default true, created_at timestamptz default now(), updated_at timestamptz default now()
);
CREATE TABLE IF NOT EXISTS products (
  id uuid primary key, company_id uuid references companies(id), description text not null, hsn_sac varchar(8), unit varchar(20), rate numeric(18,2), gst_rate numeric(5,2), taxable boolean default true, is_service boolean default false, active boolean default true, created_at timestamptz default now(), updated_at timestamptz default now()
);
CREATE TABLE IF NOT EXISTS invoices (
  id uuid primary key, gstin_id uuid not null references gstins(id), customer_id uuid references customers(id), type varchar(30) not null,
  invoice_date date not null, series varchar(30), number varchar(50) not null, place_of_supply varchar(2), reverse_charge boolean default false,
  subtotal numeric(18,2), cgst numeric(18,2), sgst numeric(18,2), igst numeric(18,2), total numeric(18,2), status varchar(30) not null default 'DRAFT',
  version integer not null default 1, created_at timestamptz default now(), updated_at timestamptz default now(), unique(gstin_id,series,number)
);
CREATE TABLE IF NOT EXISTS invoice_items (
  id uuid primary key, invoice_id uuid not null references invoices(id) on delete cascade, product_id uuid references products(id), description text,
  hsn_sac varchar(8), unit varchar(20), qty numeric(18,3), rate numeric(18,2), gst_rate numeric(5,2), taxable_value numeric(18,2),
  cgst numeric(18,2), sgst numeric(18,2), igst numeric(18,2), total numeric(18,2)
);
CREATE TABLE IF NOT EXISTS e_invoices (
  id uuid primary key, invoice_id uuid unique not null references invoices(id), irn varchar(128), irn_date timestamptz, ack_no varchar(50), ack_date timestamptz,
  signed_qr_payload text, request_json jsonb, response_json jsonb, status varchar(30), error_message text, created_at timestamptz default now(), updated_at timestamptz default now()
);
CREATE TABLE IF NOT EXISTS invoice_approvals (
  id uuid primary key, invoice_id uuid not null references invoices(id) on delete cascade, status varchar(20) not null,
  submitted_by uuid references users(id), submitted_at timestamptz, approved_by uuid references users(id), approved_at timestamptz, comment text,
  version integer not null default 1, created_at timestamptz default now(), updated_at timestamptz default now()
);
CREATE TABLE IF NOT EXISTS return_periods (
  id uuid primary key, gstin_id uuid not null references gstins(id), return_type varchar(10) not null, period varchar(7) not null,
  status varchar(20) not null default 'DRAFT', filed_on timestamptz, json_file jsonb, created_at timestamptz default now(), updated_at timestamptz default now(),
  unique(gstin_id,return_type,period)
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id uuid primary key, company_id uuid references companies(id), user_id uuid references users(id), action varchar(100), entity_type varchar(50), entity_id uuid,
  old_value jsonb, new_value jsonb, created_at timestamptz default now(), previous_hash text, event_hash text
);
CREATE TABLE IF NOT EXISTS gstr2b_entries (
  id uuid primary key, gstin_id uuid references gstins(id), vendor_gstin varchar(15) not null, vendor_name text, invoice_number varchar(50) not null,
  invoice_date date not null, taxable_value numeric(18,2) not null default 0, cgst numeric(18,2) not null default 0, sgst numeric(18,2) not null default 0,
  igst numeric(18,2) not null default 0, total numeric(18,2) not null default 0, source varchar(30) default 'IMPORT', created_at timestamptz default now(),
  unique(gstin_id,vendor_gstin,invoice_number,invoice_date)
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
  id uuid primary key, user_id uuid not null references users(id) on delete cascade, token_hash varchar(128) not null unique,
  expires_at timestamptz not null, revoked_at timestamptz, created_at timestamptz default now(), replaced_by uuid references refresh_tokens(id)
);
CREATE INDEX IF NOT EXISTS idx_gstins_company ON gstins(company_id);
CREATE INDEX IF NOT EXISTS idx_customers_company ON customers(company_id);
CREATE INDEX IF NOT EXISTS idx_vendors_company ON vendors(company_id);
CREATE INDEX IF NOT EXISTS idx_products_company_active ON products(company_id,active);
CREATE INDEX IF NOT EXISTS idx_invoices_gstin_date ON invoices(gstin_id,invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoice_approvals_invoice ON invoice_approvals(invoice_id);
CREATE INDEX IF NOT EXISTS idx_gstr2b_gstin_date ON gstr2b_entries(gstin_id,invoice_date);
CREATE INDEX IF NOT EXISTS idx_audit_company_time ON audit_logs(company_id,created_at);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);

CREATE TABLE IF NOT EXISTS gstpro_id_map (
  entity_type varchar(40) NOT NULL,
  domain_id varchar(255) NOT NULL,
  database_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_type, domain_id),
  UNIQUE (entity_type, database_id)
);
CREATE INDEX IF NOT EXISTS idx_gstpro_id_map_database ON gstpro_id_map(database_id);

CREATE INDEX IF NOT EXISTS idx_invoices_gstin_series_number ON invoices(gstin_id,series,number);
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_return_periods_gstin_period ON return_periods(gstin_id,period);
