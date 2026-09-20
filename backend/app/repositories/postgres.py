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
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    return date.fromisoformat(str(value)[:10])


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


class _Base:
    def __init__(self, store): self.store=store
    @contextmanager
    def connection(self, conn=None):
        if conn is not None: yield conn
        else:
            with self.store.connect() as connection: yield connection
    def _one(self,sql:str,params:tuple=(),conn=None):
        with self.connection(conn) as c: return c.execute(sql,params).fetchone()
    def _all(self,sql:str,params:tuple=(),conn=None):
        with self.connection(conn) as c: return c.execute(sql,params).fetchall()


class PostgresCompanyRepository(_Base):
    def list_by_company(self,company_id:str): return self._all("SELECT * FROM companies WHERE id=%s ORDER BY id",(_uuid(company_id),))
    def get(self,company_id:str): return self._one("SELECT * FROM companies WHERE id=%s",(_uuid(company_id),))
    def create(self,row:dict,conn=None):
        return self._one("""INSERT INTO companies (id,legal_name,trade_name,pan,aato,address)
                            VALUES (%s,%s,%s,%s,%s,%s::jsonb) RETURNING *""",
                         (_uuid(row.get("id") or uuid4()),row["legal_name"],row.get("trade_name"),row["pan"],_decimal(row.get("aato")),__import__("json").dumps(row.get("address") or {})),conn)
    def save(self,row:dict,conn=None):
        result=self._one("""UPDATE companies SET legal_name=%s,trade_name=%s,pan=%s,aato=%s,address=%s::jsonb,updated_at=now()
                            WHERE id=%s RETURNING *""",
                         (row["legal_name"],row.get("trade_name"),row["pan"],_decimal(row.get("aato")),__import__("json").dumps(row.get("address") or {}),_uuid(row["id"])),conn)
        return result or self.create(row,conn)


class PostgresMasterRepository(_Base):
    TABLES={"gstins":"gstins","customers":"customers","vendors":"vendors","products":"products","users":"users"}
    def list_by_company(self,kind:str,company_id:str):
        if kind not in self.TABLES: raise ValueError(f"Unsupported master kind: {kind}")
        table=self.TABLES[kind]; order="email" if kind=="users" else "id"
        return self._all(f"SELECT * FROM {table} WHERE company_id=%s ORDER BY {order}",(_uuid(company_id),))
    def list_all(self,kind:str):
        if kind not in self.TABLES: raise ValueError(f"Unsupported master kind: {kind}")
        table=self.TABLES[kind]; order="email" if kind=="users" else "id"
        return self._all(f"SELECT * FROM {table} ORDER BY {order}")
    def get(self,kind:str,entity_id:str):
        if kind not in self.TABLES: raise ValueError(f"Unsupported master kind: {kind}")
        return self._one(f"SELECT * FROM {self.TABLES[kind]} WHERE id=%s",(_uuid(entity_id),))
    def get_user_by_email(self,email:str): return self._one("SELECT * FROM users WHERE lower(email)=lower(%s)",(email.strip(),))
    def create(self,kind:str,row:dict,conn=None):
        if kind not in self.TABLES: raise ValueError(f"Unsupported master kind: {kind}")
        entity_id=_uuid(row.get("id") or uuid4()); table=self.TABLES[kind]
        if kind=="gstins":
            cols="id,company_id,gstin,state_code,scheme,legal_name,trade_name,address,is_active"
            values=(entity_id,_uuid(row["company_id"]),row["gstin"],row["state_code"],row["scheme"],row.get("legal_name"),row.get("trade_name"),__import__("json").dumps(row.get("address") or {}),row.get("is_active",True))
        elif kind in {"customers","vendors"}:
            cols="id,company_id,name,gstin,state_code,address,pan,is_active"
            values=(entity_id,_uuid(row["company_id"]),row["name"],row.get("gstin"),row.get("state_code"),__import__("json").dumps(row.get("address") or {}),row.get("pan"),row.get("is_active",True))
        elif kind=="products":
            cols="id,company_id,description,hsn_sac,unit,rate,gst_rate,taxable,is_service,active"
            values=(entity_id,_uuid(row["company_id"]),row["description"],row.get("hsn_sac"),row.get("unit"),_decimal(row.get("rate")),_decimal(row.get("gst_rate")),row.get("taxable",True),row.get("is_service",False),row.get("active",True))
        else:
            cols="id,company_id,name,email,role,password_hash,is_active,last_login_at"
            values=(entity_id,_uuid(row["company_id"]),row.get("name"),row["email"],row["role"],row["password_hash"],row.get("is_active",True),row.get("last_login_at"))
        return self._one(f"INSERT INTO {table} ({cols}) VALUES ({','.join(['%s']*len(values))}) RETURNING *",values,conn)
    def save(self,kind:str,row:dict,conn=None):
        if kind not in self.TABLES: raise ValueError(f"Unsupported master kind: {kind}")
        table=self.TABLES[kind]; entity_id=_uuid(row["id"])
        if kind=="gstins":
            sql="""UPDATE gstins SET company_id=%s,gstin=%s,state_code=%s,scheme=%s,legal_name=%s,trade_name=%s,address=%s::jsonb,is_active=%s,updated_at=now() WHERE id=%s RETURNING *"""
            values=(_uuid(row["company_id"]),row["gstin"],row["state_code"],row["scheme"],row.get("legal_name"),row.get("trade_name"),__import__("json").dumps(row.get("address") or {}),row.get("is_active",True),entity_id)
        elif kind in {"customers","vendors"}:
            sql=f"""UPDATE {table} SET company_id=%s,name=%s,gstin=%s,state_code=%s,address=%s::jsonb,pan=%s,is_active=%s,updated_at=now() WHERE id=%s RETURNING *"""
            values=(_uuid(row["company_id"]),row["name"],row.get("gstin"),row.get("state_code"),__import__("json").dumps(row.get("address") or {}),row.get("pan"),row.get("is_active",True),entity_id)
        elif kind=="products":
            sql="""UPDATE products SET company_id=%s,description=%s,hsn_sac=%s,unit=%s,rate=%s,gst_rate=%s,taxable=%s,is_service=%s,active=%s,updated_at=now() WHERE id=%s RETURNING *"""
            values=(_uuid(row["company_id"]),row["description"],row.get("hsn_sac"),row.get("unit"),_decimal(row.get("rate")),_decimal(row.get("gst_rate")),row.get("taxable",True),row.get("is_service",False),row.get("active",True),entity_id)
        else:
            sql="""UPDATE users SET company_id=%s,name=%s,email=%s,role=%s,password_hash=%s,is_active=%s,last_login_at=%s,updated_at=now() WHERE id=%s RETURNING *"""
            values=(_uuid(row["company_id"]),row.get("name"),row["email"],row["role"],row["password_hash"],row.get("is_active",True),row.get("last_login_at"),entity_id)
        result=self._one(sql,values,conn)
        return result or self.create(kind,row,conn)


class PostgresInvoiceRepository(_Base):
    def _invoice_company_id(self,invoice_id:UUID,conn=None):
        row=self._one("SELECT g.company_id FROM invoices i JOIN gstins g ON g.id=i.gstin_id WHERE i.id=%s",(invoice_id,),conn)
        return row["company_id"] if row else None

    def create(self,row:dict,conn=None):
        request=row["request"]; calc=row["calculation"]; invoice_id=_uuid(row.get("id") or uuid4()); gstin_id=_uuid(request["gstin_id"])
        company_row=self._one("SELECT company_id FROM gstins WHERE id=%s",(gstin_id,),conn)
        if not company_row or str(company_row["company_id"])!=str(request.get("company_id")): raise ValueError("GSTIN does not belong to requested company")
        company_id=company_row["company_id"]
        customer_id=None
        if request.get("customer_ref") or request.get("customer_id"):
            customer_id=_uuid(request.get("customer_ref") or request.get("customer_id"))
            if not self._one("SELECT id FROM customers WHERE id=%s AND company_id=%s",(customer_id,company_id),conn): raise ValueError("Customer reference not found in company")
        elif request.get("customer_gstin"):
            customer=self._one("SELECT id FROM customers WHERE company_id=%s AND gstin=%s LIMIT 1",(company_id,request["customer_gstin"]),conn)
            if customer: customer_id=customer["id"]
        original_invoice_id=None
        if request.get("original_invoice_id"):
            original_invoice_id=_uuid(request["original_invoice_id"])
            original=self._one("SELECT id,gstin_id,type FROM invoices WHERE id=%s",(original_invoice_id,),conn)
            if not original: raise ValueError("Original invoice not found")
            if original["gstin_id"]!=gstin_id or self._invoice_company_id(original_invoice_id,conn)!=company_id: raise ValueError("Original invoice must belong to the same GSTIN/company")
            if request.get("invoice_type") not in ("CREDIT_NOTE","DEBIT_NOTE"): raise ValueError("original_invoice_id is only valid for credit/debit notes")
        if request.get("invoice_type") in ("CREDIT_NOTE","DEBIT_NOTE") and not original_invoice_id: raise ValueError("Credit/Debit Note requires original_invoice_id")
        self._one("SELECT id FROM invoices WHERE gstin_id=%s AND series=%s AND number=%s FOR UPDATE",(gstin_id,request.get("series"),request["invoice_number"]),conn)
        self._one("""INSERT INTO invoices (id,gstin_id,customer_id,original_invoice_id,type,invoice_date,series,number,place_of_supply,reverse_charge,subtotal,cgst,sgst,igst,total,status,version)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                  (invoice_id,gstin_id,customer_id,original_invoice_id,request.get("invoice_type","TAX_INVOICE"),_date(request["invoice_date"]),request.get("series"),request["invoice_number"],request.get("place_of_supply"),request.get("reverse_charge",False),_decimal(calc.get("taxable_value")),_decimal(calc.get("cgst")),_decimal(calc.get("sgst")),_decimal(calc.get("igst")),_decimal(calc.get("total")),row.get("status","DRAFT"),1),conn)
        for line in calc.get("lines",[]):
            product_id=line.get("product_id")
            if product_id and not self._one("SELECT id FROM products WHERE id=%s AND company_id=%s AND active=true",(_uuid(product_id),company_id),conn): raise ValueError("Product reference not found in company")
            self._one("""INSERT INTO invoice_items (id,invoice_id,product_id,description,hsn_sac,unit,qty,rate,gst_rate,taxable_value,cgst,sgst,igst,total)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (uuid4(),invoice_id,_uuid(product_id) if product_id else None,line.get("description"),line.get("hsn_sac"),line.get("unit"),_decimal(line.get("qty")),_decimal(line.get("rate")),_decimal(line.get("gst_rate")),_decimal(line.get("taxable_value")),_decimal(line.get("cgst")),_decimal(line.get("sgst")),_decimal(line.get("igst")),_decimal(line.get("total"))),conn)
        return self._load(invoice_id,conn)

    def _load(self,invoice_id:UUID,conn=None,for_update=False)->Optional[dict]:
        sql="SELECT * FROM invoices WHERE id=%s"+(" FOR UPDATE" if for_update else "")
        inv=self._one(sql,(invoice_id,),conn)
        if not inv: return None
        items=self._all("SELECT * FROM invoice_items WHERE invoice_id=%s ORDER BY id",(invoice_id,),conn)
        customer=self._one("SELECT * FROM customers WHERE id=%s",(inv["customer_id"],),conn) if inv["customer_id"] else None
        gstin=self._one("SELECT * FROM gstins WHERE id=%s",(inv["gstin_id"],),conn)
        original=self._one("SELECT id,type,invoice_date,series,number,status FROM invoices WHERE id=%s",(inv["original_invoice_id"],),conn) if inv["original_invoice_id"] else None
        request={"invoice_type":inv["type"],"invoice_date":inv["invoice_date"].isoformat(),"series":inv["series"],"invoice_number":inv["number"],"original_invoice_id":str(inv["original_invoice_id"]) if inv["original_invoice_id"] else None,"place_of_supply":inv["place_of_supply"],"reverse_charge":inv["reverse_charge"],"gstin_id":str(inv["gstin_id"]),"company_id":str(gstin["company_id"]),"supplier_gstin":gstin["gstin"] if gstin else "","customer_gstin":customer["gstin"] if customer else None,"customer_name":customer["name"] if customer else "","customer_state_code":customer["state_code"] if customer else None,"scheme":gstin["scheme"] if gstin else "REGULAR","lines":[]}
        calc={"taxable_value":str(inv["subtotal"] or 0),"cgst":str(inv["cgst"] or 0),"sgst":str(inv["sgst"] or 0),"igst":str(inv["igst"] or 0),"total":str(inv["total"] or 0),"supply_type":"INTRA_STATE" if (inv["place_of_supply"]==(gstin["state_code"] if gstin else None)) else "INTER_STATE","lines":[]}
        for item in items:
            line={"product_id":str(item["product_id"]) if item["product_id"] else None,"description":item["description"],"hsn_sac":item["hsn_sac"],"unit":item["unit"],"qty":float(item["qty"] or 0),"rate":float(item["rate"] or 0),"gst_rate":float(item["gst_rate"] or 0),"taxable":True,"taxable_value":str(item["taxable_value"] or 0),"cgst":str(item["cgst"] or 0),"sgst":str(item["sgst"] or 0),"igst":str(item["igst"] or 0),"total":str(item["total"] or 0)}
            request["lines"].append({k:line[k] for k in ("product_id","description","hsn_sac","unit","qty","rate","gst_rate","taxable")}); calc["lines"].append(line)
        result={"id":str(inv["id"]),"created_at":inv["created_at"].isoformat() if inv["created_at"] else None,"request":request,"calculation":calc,"status":inv["status"]}
        if original: result["original_invoice"]={"id":str(original["id"]),"type":original["type"],"invoice_date":original["invoice_date"].isoformat(),"series":original["series"],"invoice_number":original["number"],"status":original["status"]}
        return result

    def get(self,invoice_id:str): return self._load(_uuid(invoice_id))
    def get_for_update(self,invoice_id:str,conn): return self._load(_uuid(invoice_id),conn,True)
    def list_by_company(self,company_id:str,period:Optional[str]=None):
        params=[_uuid(company_id)]; sql="SELECT i.id FROM invoices i JOIN gstins g ON g.id=i.gstin_id WHERE g.company_id=%s"
        if period: sql+=" AND to_char(i.invoice_date,'YYYY-MM')=%s"; params.append(period)
        ids=self._all(sql,tuple(params)); return [self._load(row["id"]) for row in ids]
    def save(self,row:dict,conn=None,expected_status:Optional[str]=None,immutable=True)->dict:
        invoice_id=_uuid(row["id"]); req=row["request"]; calc=row["calculation"]
        current=self._load(invoice_id,conn,for_update=conn is not None)
        if not current: return self.create(row,conn)
        if immutable and (req.get("series")!=current["request"].get("series") or req.get("invoice_number")!=current["request"].get("invoice_number")): raise ValueError("Invoice series/number is immutable after creation")
        if expected_status and current["status"]!=expected_status: raise ValueError(f"Concurrent lifecycle conflict: expected {expected_status}, found {current['status']}")
        target=row.get("status",current["status"])
        if target!=current["status"]: validate_invoice_transition(current["status"],target)
        self._one("""UPDATE invoices SET type=%s,invoice_date=%s,place_of_supply=%s,reverse_charge=%s,subtotal=%s,cgst=%s,sgst=%s,igst=%s,total=%s,status=%s,version=version+1,updated_at=now() WHERE id=%s""",
                  (req.get("invoice_type","TAX_INVOICE"),_date(req["invoice_date"]),req.get("place_of_supply"),req.get("reverse_charge",False),_decimal(calc.get("taxable_value")),_decimal(calc.get("cgst")),_decimal(calc.get("sgst")),_decimal(calc.get("igst")),_decimal(calc.get("total")),target,invoice_id),conn)
        return self._load(invoice_id,conn)

    def list_all(self): return [self.get(str(row["id"])) for row in self._all("SELECT id FROM invoices ORDER BY id")]


class InvoiceLifecycleRepository:
    def __init__(self,invoice_repo): self.invoice_repo=invoice_repo
    def transition(self,invoice_id:str,target:str,conn=None)->dict:
        current=self.invoice_repo.get_for_update(invoice_id,conn) if conn is not None else self.invoice_repo.get(invoice_id)
        if not current: raise ValueError("Invoice not found")
        validate_invoice_transition(current["status"],target)
        return self.invoice_repo.save({**current,"status":target},conn=conn,expected_status=current["status"])


class PostgresReturnRepository(_Base):
    def get(self,gstin_id:str,return_type:str,period:str): return self._one("SELECT * FROM return_periods WHERE gstin_id=%s AND return_type=%s AND period=%s",(_uuid(gstin_id),return_type,period))
    def list_by_gstin(self,gstin_id:str): return self._all("SELECT * FROM return_periods WHERE gstin_id=%s ORDER BY period,return_type",(_uuid(gstin_id),))
    def save(self,row:dict,conn=None): return self._one("""INSERT INTO return_periods (id,gstin_id,return_type,period,status,filed_on,json_file)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (gstin_id,return_type,period) DO UPDATE SET status=EXCLUDED.status,filed_on=EXCLUDED.filed_on,json_file=EXCLUDED.json_file,updated_at=now() RETURNING *""",
        (_uuid(row.get("id") or uuid4()),_uuid(row["gstin_id"]),row["return_type"],row["period"],row.get("status","DRAFT"),row.get("filed_on"),__import__("json").dumps(row.get("json_file") or {})),conn)


class PostgresApprovalRepository(_Base):
    def get(self,invoice_id:str):
        row=self._one("SELECT * FROM invoice_approvals WHERE invoice_id=%s",(_uuid(invoice_id),)); return dict(row) if row else None
    def get_for_update(self,invoice_id:str,conn):
        row=self._one("SELECT * FROM invoice_approvals WHERE invoice_id=%s FOR UPDATE",(_uuid(invoice_id),),conn); return dict(row) if row else None
    def save(self,approval:dict,conn=None):
        invoice_id=_uuid(approval["invoice_id"])
        existing=self.get_for_update(str(invoice_id),conn) if conn is not None else self.get(str(invoice_id))
        values=(approval["status"],_uuid(approval["submitted_by"]) if approval.get("submitted_by") else None,approval.get("submitted_at"),
                _uuid(approval["approved_by"]) if approval.get("approved_by") else None,approval.get("approved_at"),approval.get("comment"),invoice_id)
        if existing:
            return self._one("""UPDATE invoice_approvals SET status=%s,submitted_by=%s,submitted_at=%s,approved_by=%s,approved_at=%s,comment=%s,version=version+1,updated_at=now()
                                WHERE invoice_id=%s RETURNING *""",values,conn)
        return self._one("""INSERT INTO invoice_approvals (id,invoice_id,status,submitted_by,submitted_at,approved_by,approved_at,comment)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                         (uuid4(),invoice_id,approval["status"],_uuid(approval["submitted_by"]) if approval.get("submitted_by") else None,approval.get("submitted_at"),
                          _uuid(approval["approved_by"]) if approval.get("approved_by") else None,approval.get("approved_at"),approval.get("comment")),conn)


class PostgresPurchaseRepository(_Base):
    def list_by_company(self,company_id:str,period:Optional[str]=None):
        params=[_uuid(company_id)]; sql="SELECT e.* FROM gstr2b_entries e JOIN gstins g ON g.id=e.gstin_id WHERE g.company_id=%s"
        if period: sql+=" AND to_char(e.invoice_date,'YYYY-MM')=%s"; params.append(period)
        return self._all(sql,tuple(params))
    def create(self,row:dict,conn=None):
        return self._one("""INSERT INTO gstr2b_entries (id,gstin_id,vendor_gstin,vendor_name,invoice_number,invoice_date,taxable_value,cgst,sgst,igst,total,source)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                         (_uuid(row.get("id") or uuid4()),_uuid(row["gstin_id"]),row["vendor_gstin"],row.get("vendor_name"),row["invoice_number"],_date(row["invoice_date"]),_decimal(row.get("taxable_value")),_decimal(row.get("cgst")),_decimal(row.get("sgst")),_decimal(row.get("igst")),_decimal(row.get("total")),row.get("source","MANUAL")),conn)


class PostgresReconciliationRepository(_Base):
    def list_2b(self,company_id:str,period:str): return PostgresPurchaseRepository(self.store).list_by_company(company_id,period)
    def upsert_2b(self,row:dict,conn=None):
        existing=self._one("SELECT id FROM gstr2b_entries WHERE gstin_id=%s AND vendor_gstin=%s AND invoice_number=%s AND invoice_date=%s",(_uuid(row["gstin_id"]),row["vendor_gstin"],row["invoice_number"],_date(row["invoice_date"])),conn)
        if not existing: return PostgresPurchaseRepository(self.store).create(row,conn)
        return self._one("UPDATE gstr2b_entries SET vendor_name=%s,total=%s WHERE id=%s RETURNING *",(row.get("vendor_name"),_decimal(row.get("total")),existing["id"]),conn)


class PostgresAuditRepository(_Base):
    def append(self,row:dict,conn=None):
        return self._one("""INSERT INTO audit_logs (id,company_id,user_id,action,entity_type,entity_id,old_value,new_value,created_at,previous_hash,event_hash)
                            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s) RETURNING *""",
                         (_uuid(row.get("id") or uuid4()),_uuid(row["company_id"]) if row.get("company_id") else None,_uuid(row["user_id"]) if row.get("user_id") else None,row.get("action"),row.get("entity_type"),_uuid(row["entity_id"]) if row.get("entity_id") else None,__import__("json").dumps(row.get("old_value")) if row.get("old_value") is not None else None,__import__("json").dumps(row.get("new_value")) if row.get("new_value") is not None else None,row.get("created_at") or datetime.now(timezone.utc),row.get("previous_hash"),row.get("hash") or row.get("event_hash")),conn)
    def list_by_company(self,company_id:str):
        rows=[dict(x) for x in self._all("SELECT * FROM audit_logs WHERE company_id=%s ORDER BY created_at,id",(_uuid(company_id),))]
        for row in rows:
            if row.get("event_hash") and not row.get("hash"): row["hash"]=row["event_hash"]
        return rows


class PostgresEInvoiceRepository(_Base):
    def get(self,invoice_id:str):
        row=self._one("SELECT * FROM e_invoices WHERE invoice_id=%s",(_uuid(invoice_id),)); return dict(row) if row else None
    def save(self,row:dict,conn=None):
        return self._one("""INSERT INTO e_invoices (id,invoice_id,irn,irn_date,ack_no,ack_date,signed_qr_payload,request_json,response_json,status,error_message)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
            ON CONFLICT (invoice_id) DO UPDATE SET irn=EXCLUDED.irn,irn_date=EXCLUDED.irn_date,ack_no=EXCLUDED.ack_no,ack_date=EXCLUDED.ack_date,signed_qr_payload=EXCLUDED.signed_qr_payload,request_json=EXCLUDED.request_json,response_json=EXCLUDED.response_json,status=EXCLUDED.status,error_message=EXCLUDED.error_message,updated_at=now() RETURNING *""",
            (_uuid(row.get("id") or uuid4()),_uuid(row["invoice_id"]),row.get("irn"),row.get("irn_date"),row.get("ack_no"),row.get("ack_date"),row.get("signed_qr_payload"),__import__("json").dumps(row.get("request_json") or {}),__import__("json").dumps(row.get("response_json") or {}),row.get("status"),row.get("error_message")),conn)


INVOICE_STATES={"DRAFT":{"PENDING_APPROVAL","CANCELLED"},"PENDING_APPROVAL":{"APPROVED","REJECTED","CANCELLED"},"APPROVED":{"EINVOICE_GENERATED","CANCELLED"},"REJECTED":{"DRAFT","CANCELLED"},"EINVOICE_GENERATED":{"IRN_CANCELLED"},"IRN_CANCELLED":set(),"CANCELLED":set()}

def validate_invoice_transition(current:str,target:str)->None:
    if target not in INVOICE_STATES.get(current,set()): raise ValueError(f"Invalid invoice transition: {current} -> {target}")
