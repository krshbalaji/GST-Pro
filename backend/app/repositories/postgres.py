from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4


def _uuid(value: str | UUID) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid PostgreSQL UUID: {value!r}") from exc


def _date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


class DomainIdMapper:
    """Map human/domain identifiers to PostgreSQL UUID primary keys."""
    def __init__(self, store):
        self.store = store

    def resolve(self, entity_type: str, domain_id, conn=None) -> UUID:
        if domain_id is None:
            return None
        try:
            return _uuid(domain_id)
        except ValueError:
            pass
        with self.store.connect() if conn is None else _NullConnection(conn) as c:
            row = c.execute(
                "SELECT database_id FROM gstpro_id_map WHERE entity_type=%s AND domain_id=%s",
                (entity_type, str(domain_id)),
            ).fetchone()
            if row:
                return row["database_id"] if isinstance(row, dict) else row[0]
        raise ValueError(f"Unknown {entity_type} domain id: {domain_id}")


class _NullConnection:
    def __init__(self, conn):
        self.conn = conn
    def __enter__(self):
        return self.conn
    def __exit__(self, *args):
        return False


class _Base:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def connection(self, conn=None):
        if conn is not None:
            yield conn
            return
        with self.store.connect() as connection:
            yield connection

    def _one(self, sql: str, params: tuple = (), conn=None):
        with self.connection(conn) as c:
            return c.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = (), conn=None):
        with self.connection(conn) as c:
            return c.execute(sql, params).fetchall()

    def _execute(self, sql: str, params: tuple = (), conn=None):
        with self.connection(conn) as c:
            c.execute(sql, params)


class PostgresCompanyRepository(_Base):
    def __init__(self, store, mapper=None):
        super().__init__(store)
        self.mapper = mapper or DomainIdMapper(store)

    def list_by_company(self, company_id: str):
        company_uuid = self.mapper.resolve("company", company_id)
        return self._all(
            "SELECT * FROM companies WHERE id = %s ORDER BY id",
            (company_uuid,),
        )

    def get(self, company_id: str):
        company_uuid = self.mapper.resolve("company", company_id)
        return self._one("SELECT * FROM companies WHERE id = %s", (company_uuid,))

    def create(self, row: dict, conn=None) -> dict:
        company_id = _uuid(row.get("id") or uuid4())
        result = self._one(
            """
            INSERT INTO companies (id, legal_name, trade_name, pan, aato, address)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
            """,
            (
                company_id,
                row["legal_name"],
                row.get("trade_name"),
                row["pan"],
                _decimal(row.get("aato")),
                __import__("json").dumps(row.get("address") or {}),
            ),
            conn,
        )
        return result

    def save(self, row: dict, conn=None) -> dict:
        company_id = _uuid(row["id"])
        result = self._one(
            """
            UPDATE companies
               SET legal_name=%s, trade_name=%s, pan=%s, aato=%s, address=%s::jsonb,
                   updated_at=now()
             WHERE id=%s
             RETURNING *
            """,
            (
                row["legal_name"], row.get("trade_name"), row["pan"], _decimal(row.get("aato")),
                __import__("json").dumps(row.get("address") or {}), company_id,
            ),
            conn,
        )
        if result is None:
            return self.create(row, conn)
        return result


class PostgresMasterRepository(_Base):
    TABLES = {
        "gstins": "gstins",
        "customers": "customers",
        "vendors": "vendors",
        "products": "products",
        "users": "users",
    }
    ENTITY_TYPES = {
        "gstins": "gstin",
        "customers": "customer",
        "vendors": "vendor",
        "products": "product",
        "users": "user",
    }

    def __init__(self, store, mapper=None):
        super().__init__(store)
        self.mapper = mapper or DomainIdMapper(store)

    def resolve_company_id(self, company_id, conn=None):
        return self.mapper.resolve("company", company_id, conn)

    def resolve_entity_id(self, kind, entity_id, conn=None):
        if kind not in self.TABLES:
            raise ValueError(f"Unsupported master kind: {kind}")
        return self.mapper.resolve(self.ENTITY_TYPES[kind], entity_id, conn)

    def list_by_company(self, kind: str, company_id: str) -> list[dict]:
        company_uuid = self.resolve_company_id(company_id)
        if kind not in self.TABLES:
            raise ValueError(f"Unsupported master kind: {kind}")
        table = self.TABLES[kind]
        order = "email" if kind == "users" else "id"
        return self._all(
            f"SELECT * FROM {table} WHERE company_id = %s ORDER BY {order}",
            (company_uuid,),
        )

    def list_all(self, kind: str) -> list[dict]:
        if kind not in self.TABLES:
            raise ValueError(f"Unsupported master kind: {kind}")
        table = self.TABLES[kind]
        order = "email" if kind == "users" else "id"
        return self._all(f"SELECT * FROM {table} ORDER BY {order}")

    def get(self, kind: str, entity_id: str):
        actual_id = self.resolve_entity_id(kind, entity_id)
        table = self.TABLES[kind]
        return self._one(f"SELECT * FROM {table} WHERE id = %s", (actual_id,))

    def get_user_by_email(self, email: str):
        return self._one(
            "SELECT * FROM users WHERE lower(email)=lower(%s)",
            (email.strip(),),
        )

    def create(self, kind: str, row: dict, conn=None) -> dict:
        if kind not in self.TABLES:
            raise ValueError(f"Unsupported master kind: {kind}")
        entity_id = _uuid(row.get("id") or uuid4())
        table = self.TABLES[kind]
        if kind == "gstins":
            columns = "id,company_id,gstin,state_code,scheme,legal_name,trade_name,address,is_active"
            values = (
                entity_id, _uuid(row["company_id"]), row["gstin"], row["state_code"], row["scheme"],
                row.get("legal_name"), row.get("trade_name"),
                __import__("json").dumps(row.get("address") or {}), row.get("is_active", True),
            )
        elif kind in {"customers", "vendors"}:
            columns = "id,company_id,name,gstin,state_code,address,pan,is_active"
            values = (
                entity_id, _uuid(row["company_id"]), row["name"], row.get("gstin"), row.get("state_code"),
                __import__("json").dumps(row.get("address") or {}), row.get("pan"), row.get("is_active", True),
            )
        elif kind == "products":
            columns = "id,company_id,description,hsn_sac,unit,rate,gst_rate,taxable,is_service,active"
            values = (
                entity_id, _uuid(row["company_id"]), row["description"], row.get("hsn_sac"), row.get("unit"),
                _decimal(row.get("rate")), _decimal(row.get("gst_rate")), row.get("taxable", True),
                row.get("is_service", False), row.get("active", True),
            )
        else:
            columns = "id,company_id,name,email,role,password_hash,is_active,last_login_at"
            values = (
                entity_id, _uuid(row["company_id"]), row.get("name"), row["email"], row["role"],
                row["password_hash"], row.get("is_active", True), row.get("last_login_at"),
            )
        placeholders = ",".join(["%s"] * len(values))
        return self._one(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *",
            values,
            conn,
        )

    def save(self, kind: str, row: dict, conn=None) -> dict:
        if kind not in self.TABLES:
            raise ValueError(f"Unsupported master kind: {kind}")
        table = self.TABLES[kind]
        entity_id = _uuid(row["id"])
        if kind == "gstins":
            sql = """UPDATE gstins SET company_id=%s,gstin=%s,state_code=%s,scheme=%s,
                     legal_name=%s,trade_name=%s,address=%s::jsonb,is_active=%s,updated_at=now()
                     WHERE id=%s RETURNING *"""
            values=(_uuid(row["company_id"]),row["gstin"],row["state_code"],row["scheme"],row.get("legal_name"),
                     row.get("trade_name"),__import__("json").dumps(row.get("address") or {}),row.get("is_active",True),entity_id)
        elif kind in {"customers","vendors"}:
            sql=f"""UPDATE {table} SET company_id=%s,name=%s,gstin=%s,state_code=%s,address=%s::jsonb,
                     pan=%s,is_active=%s,updated_at=now() WHERE id=%s RETURNING *"""
            values=(_uuid(row["company_id"]),row["name"],row.get("gstin"),row.get("state_code"),
                    __import__("json").dumps(row.get("address") or {}),row.get("pan"),row.get("is_active",True),entity_id)
        elif kind=="products":
            sql="""UPDATE products SET company_id=%s,description=%s,hsn_sac=%s,unit=%s,rate=%s,gst_rate=%s,
                     taxable=%s,is_service=%s,active=%s,updated_at=now() WHERE id=%s RETURNING *"""
            values=(_uuid(row["company_id"]),row["description"],row.get("hsn_sac"),row.get("unit"),_decimal(row.get("rate")),
                    _decimal(row.get("gst_rate")),row.get("taxable",True),row.get("is_service",False),row.get("active",True),entity_id)
        else:
            sql="""UPDATE users SET company_id=%s,name=%s,email=%s,role=%s,password_hash=%s,is_active=%s,
                     last_login_at=%s,updated_at=now() WHERE id=%s RETURNING *"""
            values=(_uuid(row["company_id"]),row.get("name"),row["email"],row["role"],row["password_hash"],
                    row.get("is_active",True),row.get("last_login_at"),entity_id)
        result=self._one(sql,values,conn)
        return result or self.create(kind,row,conn)


class InvoiceLifecycleRepository(_Base):
    """PostgreSQL-backed invoice lifecycle locking and transition contract."""

    def __init__(self, store, mapper=None):
        super().__init__(store)
        self.mapper = mapper or DomainIdMapper(store)

    def lock(self, invoice_id: str, conn=None):
        """Lock an invoice row for an atomic lifecycle decision."""
        actual_id = self.mapper.resolve("invoice", invoice_id, conn)
        return self._one(
            "SELECT id, status, version FROM invoices WHERE id=%s FOR UPDATE",
            (actual_id,),
            conn,
        )

    @staticmethod
    def validate(current: str, target: str) -> None:
        validate_invoice_transition(current, target)


class PostgresInvoiceRepository(_Base):
    def __init__(self, store, mapper=None):
        super().__init__(store)
        self.mapper = mapper or DomainIdMapper(store)

    def create(self, row: dict, conn=None) -> dict:
        request = row["request"]
        calc = row["calculation"]
        requested_id = row.get("id")
        invoice_id = _uuid(requested_id) if requested_id else uuid4()
        customer_id = request.get("customer_id") or request.get("customer_ref")
        gstin_uuid = self.mapper.resolve("gstin", request["gstin_id"], conn)
        company_uuid = None
        if customer_id and request.get("company_id"):
            company_uuid = self.mapper.resolve("company", request["company_id"], conn)
        if not customer_id and request.get("customer_gstin"):
            customer = self._one(
                "SELECT id FROM customers WHERE company_id=%s AND gstin=%s LIMIT 1",
                (company_uuid or self._one("SELECT company_id FROM gstins WHERE id=%s",(gstin_uuid,),conn)["company_id"], request["customer_gstin"]),
                conn,
            )
            customer_id = customer["id"] if customer else None
        created = self._one(
            """
            INSERT INTO invoices
              (id,gstin_id,customer_id,type,invoice_date,series,number,place_of_supply,reverse_charge,
               subtotal,cgst,sgst,igst,total,status,version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                invoice_id,gstin_uuid,self.mapper.resolve("customer", customer_id, conn) if customer_id else None,
                request.get("invoice_type","TAX_INVOICE"),_date(request["invoice_date"]),request.get("series"),
                request["invoice_number"],request.get("place_of_supply"),request.get("reverse_charge",False),
                _decimal(calc.get("taxable_value")), _decimal(calc.get("cgst")), _decimal(calc.get("sgst")),
                _decimal(calc.get("igst")), _decimal(calc.get("total")), row.get("status","DRAFT"), 1,
            ),
            conn,
        )
        for line in calc.get("lines", []):
            product_id = line.get("product_id")
            product_uuid = self.mapper.resolve("product", product_id, conn) if product_id else None
            self._execute(
                """
                INSERT INTO invoice_items
                  (id,invoice_id,product_id,description,hsn_sac,unit,qty,rate,gst_rate,taxable_value,cgst,sgst,igst,total)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    uuid4(), invoice_id, product_uuid, line.get("description"),
                    line.get("hsn_sac"), line.get("unit"), _decimal(line.get("qty")), _decimal(line.get("rate")),
                    _decimal(line.get("gst_rate")), _decimal(line.get("taxable_value")), _decimal(line.get("cgst")),
                    _decimal(line.get("sgst")), _decimal(line.get("igst")), _decimal(line.get("total")),
                ),
                conn,
            )
        return self._load(invoice_id, conn=conn)

    def _load(self, invoice_id: UUID, conn=None) -> Optional[dict]:
        inv = self._one("SELECT * FROM invoices WHERE id=%s", (invoice_id,), conn)
        if not inv:
            return None
        items = self._all("SELECT * FROM invoice_items WHERE invoice_id=%s ORDER BY id", (invoice_id,), conn)
        customer = None
        if inv["customer_id"]:
            customer = self._one("SELECT * FROM customers WHERE id=%s", (inv["customer_id"],), conn)
        gstin = self._one("SELECT * FROM gstins WHERE id=%s", (inv["gstin_id"],), conn)
        request = {
            "invoice_type": inv["type"], "invoice_date": inv["invoice_date"].isoformat(),
            "series": inv["series"], "invoice_number": inv["number"], "place_of_supply": inv["place_of_supply"],
            "reverse_charge": inv["reverse_charge"], "gstin_id": str(inv["gstin_id"]), "company_id": str(gstin["company_id"]),
            "supplier_gstin": gstin["gstin"] if gstin else "",
            "customer_gstin": customer["gstin"] if customer else None,
            "customer_name": customer["name"] if customer else "",
            "customer_state_code": customer["state_code"] if customer else None,
            "scheme": gstin["scheme"] if gstin else "REGULAR",
            "lines": [],
        }
        calc = {
            "taxable_value": str(inv["subtotal"] or 0), "cgst": str(inv["cgst"] or 0), "sgst": str(inv["sgst"] or 0),
            "igst": str(inv["igst"] or 0), "total": str(inv["total"] or 0),
            "supply_type": "INTRA_STATE" if (inv["place_of_supply"] == (gstin["state_code"] if gstin else None)) else "INTER_STATE",
            "lines": [],
        }
        for item in items:
            line = {
                "product_id": str(item["product_id"]) if item["product_id"] else None,
                "description": item["description"], "hsn_sac": item["hsn_sac"], "unit": item["unit"],
                "qty": float(item["qty"] or 0), "rate": float(item["rate"] or 0), "gst_rate": float(item["gst_rate"] or 0),
                "taxable": True, "taxable_value": str(item["taxable_value"] or 0), "cgst": str(item["cgst"] or 0),
                "sgst": str(item["sgst"] or 0), "igst": str(item["igst"] or 0), "total": str(item["total"] or 0),
            }
            request["lines"].append({k: line[k] for k in ("product_id","description","hsn_sac","unit","qty","rate","gst_rate","taxable")})
            calc["lines"].append(line)
        return {
            "id": str(inv["id"]), "created_at": inv["created_at"].isoformat() if inv["created_at"] else None,
            "request": request, "calculation": calc, "status": inv["status"],
        }

    def get(self, invoice_id: str):
        return self._load(self.mapper.resolve("invoice", invoice_id))

    def list_by_company(self, company_id: str, period: Optional[str]=None):
        company_uuid=self.mapper.resolve("company", company_id)
        params=[company_uuid]
        sql="SELECT i.id FROM invoices i JOIN gstins g ON g.id=i.gstin_id WHERE g.company_id=%s"
        if period:
            sql+=" AND to_char(i.invoice_date,'YYYY-MM')=%s"
            params.append(period)
        ids=self._all(sql,tuple(params))
        return [self._load(row["id"]) for row in ids]

    def save(self, row: dict, conn=None) -> dict:
        invoice_id=self.mapper.resolve("invoice", row["id"], conn)
        req=row["request"]; calc=row["calculation"]
        current=self._one("SELECT status,version FROM invoices WHERE id=%s FOR UPDATE",(invoice_id,),conn)
        if current is None:
            return self.create(row,conn)
        if row.get("status") and row["status"] != current["status"]:
            validate_invoice_transition(current["status"], row["status"])
        updated=self._one(
            """UPDATE invoices SET type=%s,invoice_date=%s,series=%s,number=%s,place_of_supply=%s,
                     reverse_charge=%s,subtotal=%s,cgst=%s,sgst=%s,igst=%s,total=%s,status=%s,
                     version=version+1,updated_at=now() WHERE id=%s AND version=%s RETURNING id""",
            (
                req.get("invoice_type","TAX_INVOICE"),_date(req["invoice_date"]),req.get("series"),req["invoice_number"],
                req.get("place_of_supply"),req.get("reverse_charge",False),_decimal(calc.get("taxable_value")),
                _decimal(calc.get("cgst")), _decimal(calc.get("sgst")), _decimal(calc.get("igst")), _decimal(calc.get("total")),
                row.get("status",current["status"]), invoice_id, current["version"],
            ),
            conn,
        )
        if not updated:
            raise ValueError("Invoice was modified concurrently; reload before saving.")
        return self._load(invoice_id,conn=conn)

    def list_all(self):
        ids = self._all("SELECT id FROM invoices ORDER BY id")
        return [self.get(str(row["id"])) for row in ids]

    def delete(self, invoice_id: str, conn=None):
        actual_id = self.mapper.resolve("invoice", invoice_id, conn)
        with self.connection(conn) as c:
            row = c.execute("SELECT status FROM invoices WHERE id=%s FOR UPDATE",(actual_id,)).fetchone()
            if not row:
                return False
            validate_invoice_transition(row["status"], "CANCELLED")
            c.execute("UPDATE invoices SET status='CANCELLED',version=version+1,updated_at=now() WHERE id=%s",(actual_id,))
            return True


class PostgresApprovalRepository(_Base):
    def __init__(self, store, mapper=None):
        super().__init__(store)
        self.mapper = mapper or DomainIdMapper(store)

    def _normalize(self, row):
        if not row:
            return None
        return {
            "id": str(row["id"]),
            "invoice_id": str(row["invoice_id"]),
            "status": row["status"],
            "submitted_by": str(row["submitted_by"]) if row.get("submitted_by") else None,
            "submitted_at": row["submitted_at"].isoformat() if row.get("submitted_at") else None,
            "approved_by": str(row["approved_by"]) if row.get("approved_by") else None,
            "approved_at": row["approved_at"].isoformat() if row.get("approved_at") else None,
            "comment": row.get("comment") or "",
        }

    def get(self, invoice_id:str):
        actual_id=self.mapper.resolve("invoice",invoice_id)
        return self._normalize(self._one("SELECT * FROM invoice_approvals WHERE invoice_id=%s",(actual_id,)))

    def save(self, approval:dict, conn=None):
        invoice_id=self.mapper.resolve("invoice",approval["invoice_id"],conn)
        existing=self._one(
            "SELECT * FROM invoice_approvals WHERE invoice_id=%s FOR UPDATE",(invoice_id,),conn
        ) if conn is not None else self.get(str(invoice_id))
        if existing:
            result = self._one(
                """UPDATE invoice_approvals SET status=%s,submitted_by=%s,submitted_at=%s,approved_by=%s,
                       approved_at=%s,comment=%s,version=version+1,updated_at=now() WHERE invoice_id=%s RETURNING *""",
                (approval["status"],self.mapper.resolve("user",approval["submitted_by"],conn) if approval.get("submitted_by") else None,
                 approval.get("submitted_at"),self.mapper.resolve("user",approval["approved_by"],conn) if approval.get("approved_by") else None,
                 approval.get("approved_at"),approval.get("comment"),invoice_id),
                conn,
            )
        else:
            result = self._one(
                """INSERT INTO invoice_approvals
                   (id,invoice_id,status,submitted_by,submitted_at,approved_by,approved_at,comment)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (uuid4(),invoice_id,approval["status"],self.mapper.resolve("user",approval["submitted_by"],conn) if approval.get("submitted_by") else None,
                 approval.get("submitted_at"),self.mapper.resolve("user",approval["approved_by"],conn) if approval.get("approved_by") else None,
                 approval.get("approved_at"),approval.get("comment")),
                conn,
            )
        return self._normalize(result)

    def list_by_company(self,company_id:str,invoice_lookup=None):
        company_uuid=self.mapper.resolve("company",company_id)
        return self._all(
            """SELECT a.* FROM invoice_approvals a
               JOIN invoices i ON i.id=a.invoice_id
               JOIN gstins g ON g.id=i.gstin_id
               WHERE g.company_id=%s ORDER BY a.created_at""",
            (company_uuid,),
        )


class PostgresPurchaseRepository(_Base):
    def __init__(self, store, mapper=None):
        super().__init__(store)
        self.mapper = mapper or DomainIdMapper(store)

    def list_by_company(self,company_id:str,period:Optional[str]=None):
        company_uuid=self.mapper.resolve("company",company_id)
        params=[company_uuid]
        sql="SELECT e.* FROM gstr2b_entries e JOIN gstins g ON g.id=e.gstin_id WHERE g.company_id=%s"
        if period:
            sql+=" AND to_char(e.invoice_date,'YYYY-MM')=%s"
            params.append(period)
        return self._all(sql,tuple(params))

    def create(self,row:dict,conn=None):
        entry_id=_uuid(row.get("id") or uuid4())
        return self._one(
            """INSERT INTO gstr2b_entries
               (id,gstin_id,vendor_gstin,vendor_name,invoice_number,invoice_date,taxable_value,cgst,sgst,igst,total,source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (entry_id,self.mapper.resolve("gstin",row["gstin_id"],conn),row["vendor_gstin"],row.get("vendor_name"),row["invoice_number"],
             _date(row["invoice_date"]),_decimal(row.get("taxable_value")),_decimal(row.get("cgst")),_decimal(row.get("sgst")),
             _decimal(row.get("igst")),_decimal(row.get("total")),row.get("source","MANUAL")),
            conn,
        )

    def save(self,row:dict,conn=None):
        entry_id=_uuid(row["id"])
        return self._one(
            """UPDATE gstr2b_entries SET gstin_id=%s,vendor_gstin=%s,vendor_name=%s,invoice_number=%s,
                     invoice_date=%s,taxable_value=%s,cgst=%s,sgst=%s,igst=%s,total=%s,source=%s
               WHERE id=%s RETURNING *""",
            (self.mapper.resolve("gstin",row["gstin_id"],conn),row["vendor_gstin"],row.get("vendor_name"),row["invoice_number"],_date(row["invoice_date"]),
             _decimal(row.get("taxable_value")),_decimal(row.get("cgst")),_decimal(row.get("sgst")),_decimal(row.get("igst")),_decimal(row.get("total")),
             row.get("source","MANUAL"),entry_id),
            conn,
        )

    def delete(self,entry_id:str,conn=None):
        with self.connection(conn) as c:
            c.execute("DELETE FROM gstr2b_entries WHERE id=%s",(self.mapper.resolve("gstr2b_entry",entry_id,conn),))


class PostgresReconciliationRepository(_Base):
    def __init__(self, store, mapper=None):
        super().__init__(store)
        self.mapper=mapper or DomainIdMapper(store)

    def list_2b(self,company_id:str,period:str):
        return PostgresPurchaseRepository(self.store,self.mapper).list_by_company(company_id,period)

    def upsert_2b(self,row:dict,conn=None):
        gstin_uuid=self.mapper.resolve("gstin",row["gstin_id"],conn)
        existing=self._one(
            """SELECT id FROM gstr2b_entries
               WHERE gstin_id=%s AND vendor_gstin=%s AND invoice_number=%s AND invoice_date=%s""",
            (gstin_uuid,row["vendor_gstin"],row["invoice_number"],_date(row["invoice_date"])),conn,
        )
        normalized=dict(row)
        normalized["gstin_id"]=gstin_uuid
        return PostgresPurchaseRepository(self.store,self.mapper).save(normalized,conn) if existing else PostgresPurchaseRepository(self.store,self.mapper).create(normalized,conn)


class PostgresAuditRepository(_Base):
    def __init__(self, store, mapper=None):
        super().__init__(store)
        self.mapper = mapper or DomainIdMapper(store)

    def append(self,row:dict,conn=None):
        company_id=row.get("company_id")
        user_id=row.get("user_id")
        entity_id=row.get("entity_id")
        entity_type=str(row.get("entity_type") or "").lower()

        def _json(value):
            return __import__("json").dumps(value, sort_keys=True, default=str) if value is not None else None

        entity_uuid = None
        if entity_id and entity_type in {
            "company", "gstin", "user", "customer", "vendor", "product", "invoice", "approval",
        }:
            entity_uuid = self.mapper.resolve(entity_type, entity_id, conn)

        return self._one(
            """INSERT INTO audit_logs
               (id,company_id,user_id,action,entity_type,entity_id,old_value,new_value,created_at,previous_hash,event_hash)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s) RETURNING *""",
            (
                _uuid(row.get("id") or uuid4()),
                self.mapper.resolve("company",company_id,conn) if company_id else None,
                self.mapper.resolve("user",user_id,conn) if user_id else None,
                row.get("action"),row.get("entity_type"),
                entity_uuid,
                _json(row.get("old_value")),
                _json(row.get("new_value")),
                row.get("created_at") or datetime.now(timezone.utc),
                row.get("previous_hash"),row.get("hash") or row.get("event_hash"),
            ),
            conn,
        )

    def list_by_company(self,company_id:str):
        company_uuid=self.mapper.resolve("company",company_id)
        rows=self._all("SELECT * FROM audit_logs WHERE company_id=%s ORDER BY created_at,id",(company_uuid,))
        return [self._normalize(row) for row in rows]

    @staticmethod
    def _normalize(row):
        out=dict(row)
        if out.get("event_hash") and not out.get("hash"):
            out["hash"]=out["event_hash"]
        return out


class PostgresReturnRepository(_Base):
    def __init__(self, store, mapper=None):
        super().__init__(store)
        self.mapper=mapper or DomainIdMapper(store)

    def get(self,gstin_id:str,return_type:str,period:str):
        return self._one(
            "SELECT * FROM return_periods WHERE gstin_id=%s AND return_type=%s AND period=%s",
            (self.mapper.resolve("gstin",gstin_id),return_type,period),
        )

    def list_by_gstin(self,gstin_id:str):
        return self._all(
            "SELECT * FROM return_periods WHERE gstin_id=%s ORDER BY period,return_type",
            (self.mapper.resolve("gstin",gstin_id),),
        )

    def save(self,row:dict,conn=None):
        row_id=_uuid(row.get("id") or uuid4())
        return self._one(
            """
            INSERT INTO return_periods (id,gstin_id,return_type,period,status,filed_on,json_file)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (gstin_id,return_type,period)
            DO UPDATE SET status=EXCLUDED.status,filed_on=EXCLUDED.filed_on,json_file=EXCLUDED.json_file,updated_at=now()
            RETURNING *
            """,
            (row_id,self.mapper.resolve("gstin",row["gstin_id"],conn),row["return_type"],row["period"],row.get("status","DRAFT"),
             row.get("filed_on"),__import__("json").dumps(row.get("json_file") or {})),
            conn,
        )


class PostgresTransactionRepository:
    def __init__(self, store, repos):
        self.store = store
        self.repos = repos

    @contextmanager
    def transaction(self):
        with self.store.connect() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def create_invoice_with_audit(self,row,audit_row):
        with self.transaction() as conn:
            invoice=self.repos["invoices"].create(row,conn=conn)
            audit_row=dict(audit_row); audit_row["entity_id"]=invoice["id"]
            self.repos["audit"].append(audit_row,conn=conn)
            return invoice

    def transition_with_approval_and_audit(self,invoice_id,approval_row,audit_row,target_status):
        with self.transaction() as conn:
            invoice_repo=self.repos["invoices"]
            current_id=invoice_repo.mapper.resolve("invoice",invoice_id,conn)
            current=invoice_repo._load(current_id,conn=conn)
            if not current: raise ValueError("Invoice not found")
            validate_invoice_transition(current.get("status","DRAFT"),target_status)
            target=dict(current); target["status"]=target_status
            invoice=invoice_repo.save(target,conn=conn)
            approval=self.repos["approvals"].save(approval_row,conn=conn)
            self.repos["audit"].append({**audit_row,"entity_id":invoice["id"]},conn=conn)
            return invoice,approval

    def submit_invoice(self,invoice_id,approval_row,audit_row):
        with self.transaction() as conn:
            invoice_repo=self.repos["invoices"]
            current_id=invoice_repo.mapper.resolve("invoice",invoice_id,conn)
            current=invoice_repo._load(current_id,conn=conn)
            if not current: raise ValueError("Invoice not found")
            validate_invoice_transition(current.get("status","DRAFT"),"PENDING_APPROVAL")
            target=dict(current); target["status"]="PENDING_APPROVAL"
            invoice=invoice_repo.save(target,conn=conn)
            approval=self.repos["approvals"].save(approval_row,conn=conn)
            self.repos["audit"].append({**audit_row,"entity_id":invoice["id"]},conn=conn)
            return invoice,approval

    def decide_invoice(self,invoice_id,approval_row,audit_row,target_status):
        return self.transition_with_approval_and_audit(invoice_id,approval_row,audit_row,target_status)


INVOICE_STATES={
    "DRAFT":{"PENDING_APPROVAL","CANCELLED"},
    "PENDING_APPROVAL":{"APPROVED","REJECTED","CANCELLED"},
    "APPROVED":{"EINVOICE_GENERATED","CANCELLED"},
    "REJECTED":{"DRAFT","CANCELLED"},
    "EINVOICE_GENERATED":{"IRN_CANCELLED"},
    "IRN_CANCELLED":set(),
    "CANCELLED":set(),
}


def validate_invoice_transition(current: str, target: str) -> None:
    if target not in INVOICE_STATES.get(current, set()):
        raise ValueError(f"Invalid invoice transition: {current} -> {target}")
