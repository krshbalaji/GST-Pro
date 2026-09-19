import csv, hashlib, io, json, os, uuid, copy
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional
import jwt
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from .gst import calculate_invoice, Scheme, hsn_min_digits, financial_year
from .storage import store
from .security import hash_password, verify_password, make_token, decode_token, ROLES
from .einvoice import MockIRPProvider

app=FastAPI(title='GST Pro API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

RATE_PRESETS={
 'REGULAR_5':{'name':'5% Regular','scheme':'REGULAR','rate':5},
 'REGULAR_12':{'name':'12% Regular','scheme':'REGULAR','rate':12},
 'REGULAR_18':{'name':'18% Regular','scheme':'REGULAR','rate':18},
 'REGULAR_28':{'name':'28% Regular','scheme':'REGULAR','rate':28},
 'COMPOSITION_1':{'name':'1% Composition (configurable)','scheme':'COMPOSITION','rate':1},
 'COMPOSITION_5':{'name':'5% Composition (configurable)','scheme':'COMPOSITION','rate':5},
 'COMPOSITION_6':{'name':'6% Composition (configurable)','scheme':'COMPOSITION','rate':6},
 'EXEMPT':{'name':'Exempt / Nil-rated','scheme':'REGULAR','rate':0},
}

STATE_CODES={'01':'Jammu & Kashmir','02':'Himachal Pradesh','03':'Punjab','04':'Chandigarh','05':'Uttarakhand','06':'Haryana','07':'Delhi','08':'Rajasthan','09':'Uttar Pradesh','10':'Bihar','11':'Sikkim','12':'Arunachal Pradesh','13':'Nagaland','14':'Manipur','15':'Mizoram','16':'Tripura','17':'Meghalaya','18':'Assam','19':'West Bengal','20':'Jharkhand','21':'Odisha','22':'Chhattisgarh','23':'Madhya Pradesh','24':'Gujarat','27':'Maharashtra','29':'Karnataka','30':'Goa','32':'Kerala','33':'Tamil Nadu','34':'Puducherry','35':'Andaman & Nicobar Islands','36':'Telangana','37':'Andhra Pradesh','38':'Ladakh','97':'Other Territory'}

# In-memory repository keeps the demo immediately runnable. The PostgreSQL schema in /database is the persistence target.
COMPANIES={}; GSTINS={}; CUSTOMERS={}; VENDORS={}; PRODUCTS={}; USERS={}; INVOICES={}; PURCHASES={}; AUDIT=[]; RETURNS={}; APPROVALS={}
PURCHASES_2B={}
SECRET=os.getenv('JWT_SECRET','gst-pro-production-secret-change-me-please-set-env')

class Line(BaseModel):
    model_config=ConfigDict(extra='forbid')
    product_id:str|None=None; description:str; hsn_sac:str; unit:str; qty:float=Field(gt=0); rate:float=Field(ge=0); gst_rate:float=Field(ge=0); taxable:bool=True

class InvoiceRequest(BaseModel):
    invoice_type:str='TAX_INVOICE'; scheme:Scheme=Scheme.REGULAR; supplier_state_code:str; place_of_supply:str; supplier_gstin:str
    customer_gstin:str|None=None; customer_name:str; customer_state_code:str|None=None; invoice_date:str; series:str='SDE'; invoice_number:str
    lines:list[Line]=Field(min_length=1); reverse_charge:bool=False; company_id:str='demo-company'; gstin_id:str='demo-gstin'; notes:str=''

class PartyRequest(BaseModel):
    company_id:str='demo-company'; name:str; gstin:str|None=None; state_code:str|None=None; address:dict={}; pan:str|None=None

class ProductRequest(BaseModel):
    company_id:str='demo-company'; description:str; hsn_sac:str; unit:str; rate:float=Field(ge=0); gst_rate:float=Field(ge=0); is_service:bool=False; active:bool=True

class PurchaseRequest(BaseModel):
    company_id:str='demo-company'; gstin_id:str='demo-gstin'; vendor_name:str; vendor_gstin:str|None=None; invoice_number:str; invoice_date:str; taxable_value:float; cgst:float=0; sgst:float=0; igst:float=0; total:float; source:str='MANUAL'; itc_eligible:bool=True

class GSTR2BRow(BaseModel): company_id:str='demo-company'; gstin_id:str='demo-gstin'; vendor_gstin:str; vendor_name:str=''; invoice_number:str; invoice_date:str; taxable_value:float; cgst:float=0; sgst:float=0; igst:float=0; total:float=0
class AuthRequest(BaseModel): email:str; password:str
class EinvoiceRequest(BaseModel): invoice_id:str
class ReturnLockRequest(BaseModel): gstin_id:str='demo-gstin'; return_type:str; period:str


def audit(action, entity_type, entity_id, new=None, old=None, company_id='demo-company', user_id=None):
    previous=AUDIT[-1]['hash'] if AUDIT else 'GENESIS'
    payload={'action':action,'entity_type':entity_type,'entity_id':entity_id,'old_value':copy.deepcopy(old),'new_value':copy.deepcopy(new),'company_id':company_id,'user_id':user_id,'created_at':datetime.now(timezone.utc).isoformat(),'previous_hash':previous}
    payload['hash']=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
    AUDIT.append({'id':str(uuid.uuid4()),**payload})

def persist_state():
    store.save({
        'companies':COMPANIES,'gstins':GSTINS,'customers':CUSTOMERS,'vendors':VENDORS,
        'products':PRODUCTS,'users':USERS,'invoices':INVOICES,'purchases':PURCHASES,
        'purchases_2b':PURCHASES_2B,'audit':AUDIT,'returns':RETURNS,'approvals':APPROVALS
    })

def restore_state():
    if not store.enabled: return
    state=store.load()
    for name,target in [('companies',COMPANIES),('gstins',GSTINS),('customers',CUSTOMERS),('vendors',VENDORS),('products',PRODUCTS),('users',USERS),('invoices',INVOICES),('purchases',PURCHASES),('purchases_2b',PURCHASES_2B),('audit',AUDIT),('returns',RETURNS),('approvals',APPROVALS)]:
        data=state.get(name)
        if data is not None:
            if isinstance(target,dict): target.update(data)
            else: target.extend(data)

def seed():
    if COMPANIES: return
    COMPANIES['demo-company']={'id':'demo-company','legal_name':'SARO DEVI ENTERPRISES','trade_name':'Saro Devi Enterprises','pan':'ABCDE1234F','address':{'line1':'123, North Veli Street','city':'Madurai','state':'Tamil Nadu','pincode':'625001'},'aato':45000000}
    GSTINS['demo-gstin']={'id':'demo-gstin','company_id':'demo-company','gstin':'33ABCDE1234F1Z5','state_code':'33','scheme':'REGULAR','legal_name':'SARO DEVI ENTERPRISES','trade_name':'Saro Devi Enterprises','aato':45000000,'e_invoice_enabled':True}
    CUSTOMERS['C1']={'id':'C1','company_id':'demo-company','name':'ABC Traders','gstin':'33AACFA1234A1Z1','state_code':'33','address':{'line1':'123, Anna Salai','city':'Chennai','state':'Tamil Nadu','pincode':'600002'}}
    CUSTOMERS['C2']={'id':'C2','company_id':'demo-company','name':'Bharat Karnataka Stores','gstin':'29AACFA1234A1Z1','state_code':'29','address':{'line1':'MG Road','city':'Bengaluru','state':'Karnataka','pincode':'560001'}}
    PRODUCTS.update({'P1':{'id':'P1','company_id':'demo-company','description':'Cotton Shirt (Men)','hsn_sac':'620520','unit':'PCS','rate':500,'gst_rate':18,'is_service':False,'active':True},'P2':{'id':'P2','company_id':'demo-company','description':'Towel (Home Textile)','hsn_sac':'630260','unit':'PCS','rate':300,'gst_rate':12,'is_service':False,'active':True},'P3':{'id':'P3','company_id':'demo-company','description':'IT Consulting','hsn_sac':'998313','unit':'HRS','rate':2500,'gst_rate':18,'is_service':True,'active':True}})
    USERS['U1']={'id':'U1','company_id':'demo-company','name':'Admin','email':'admin@gstpro.local','role':'OWNER','password_hash':hash_password('admin')}
    USERS['U2']={'id':'U2','company_id':'demo-company','name':'Demo CA','email':'ca@gstpro.local','role':'CA','password_hash':hash_password('caadmin123')}
store.init()
restore_state()
seed()
if store.enabled and not store.load(): persist_state()

def current_user(authorization: str = Header(default='')):
    if not authorization.startswith('Bearer '):
        raise HTTPException(401,'Authentication required')
    try:
        return decode_token(authorization[7:])
    except Exception:
        raise HTTPException(401,'Invalid or expired access token')

def require_permission(permission:str):
    def dep(user=Depends(current_user)):
        if permission not in ROLES.get(user.get('role'), set()):
            raise HTTPException(403,f'Role {user.get("role")} cannot perform {permission}')
        return user
    return dep

def company_scope(user, company_id:str):
    if user.get('company_id')!=company_id:
        raise HTTPException(403,'Cross-company access denied')

def ensure_period_open(gstin_id:str, invoice_date:str):
    period=invoice_date[:7]
    for x in RETURNS.values():
        if x.get('gstin_id')==gstin_id and x.get('period')==period and x.get('status')=='LOCKED':
            raise HTTPException(409,f'Return period {period} is locked for {x.get("return_type")}; invoice changes are blocked.')

def validate_invoice(req:InvoiceRequest):
    if req.invoice_type=='TAX_INVOICE' and req.scheme==Scheme.COMPOSITION: raise HTTPException(422,'Composition taxpayers must issue a Bill of Supply; GST must not be charged to the customer.')
    if req.scheme==Scheme.COMPOSITION and req.invoice_type not in ('BILL_OF_SUPPLY','CREDIT_NOTE','DEBIT_NOTE'): raise HTTPException(422,'Composition supply requires Bill of Supply.')
    if len(req.supplier_gstin)!=15: raise HTTPException(422,'Supplier GSTIN must be 15 characters.')
    if req.supplier_gstin[:2]!=req.supplier_state_code: raise HTTPException(422,'Supplier state code does not match GSTIN.')
    for l in req.lines:
        if len(l.hsn_sac)>8: raise HTTPException(422,'HSN/SAC cannot exceed 8 digits.')
        min_digits=hsn_min_digits(COMPANIES.get(req.company_id,{}).get('aato',0))
        if l.hsn_sac and len(''.join(c for c in l.hsn_sac if c.isdigit())) < min_digits: raise HTTPException(422,f'HSN/SAC requires at least {min_digits} digits for this AATO.')
    return calculate_invoice([x.model_dump() for x in req.lines],req.scheme,req.supplier_state_code,req.place_of_supply)

def invoice_row(req, calc, status='DRAFT'):
    iid=str(uuid.uuid4()); row={'id':iid,'created_at':datetime.now(timezone.utc).isoformat(),'request':req.model_dump(),'calculation':{k:str(v) if isinstance(v,Decimal) else v for k,v in calc.items()},'status':status}
    INVOICES[iid]=row; audit('CREATE','INVOICE',iid,row); persist_state(); return row

@app.get('/health')
def health(): return {'status':'ok','service':'gst-pro','version':'1.2.0','database':store.health()}
@app.get('/api/config')
def config():
    return {'e_invoice_threshold':50000000,'e_invoice_30day_threshold':100000000,'hsn_threshold':50000000,'hsn_min_digits_below_or_equal':4,'hsn_min_digits_above':6,'state_codes':STATE_CODES}
@app.get('/api/gst-rate-presets')
def presets(): return RATE_PRESETS
@app.get('/api/companies')
def companies(): return list(COMPANIES.values())
@app.get('/api/gstins')
def gstins(company_id:str='demo-company'): return [x for x in GSTINS.values() if x['company_id']==company_id]
@app.get('/api/customers')
def customers(company_id:str='demo-company'): return [x for x in CUSTOMERS.values() if x['company_id']==company_id]
@app.post('/api/customers')
def create_customer(req:PartyRequest,user=Depends(require_permission('create'))):
    company_scope(user,req.company_id)
    cid=str(uuid.uuid4()); row={'id':cid,**req.model_dump()}; CUSTOMERS[cid]=row; audit('CREATE','CUSTOMER',cid,row); persist_state(); return row
@app.get('/api/vendors')
def vendors(company_id:str='demo-company'): return [x for x in VENDORS.values() if x['company_id']==company_id]
@app.post('/api/vendors')
def create_vendor(req:PartyRequest,user=Depends(require_permission('create'))):
    company_scope(user,req.company_id)
    vid=str(uuid.uuid4()); row={'id':vid,**req.model_dump()}; VENDORS[vid]=row; audit('CREATE','VENDOR',vid,row); persist_state(); return row
@app.get('/api/products')
def products(company_id:str='demo-company'): return [x for x in PRODUCTS.values() if x['company_id']==company_id and x.get('active',True)]
@app.post('/api/products')
def create_product(req:ProductRequest,user=Depends(require_permission('create'))):
    company_scope(user,req.company_id)
    pid=str(uuid.uuid4()); row={'id':pid,**req.model_dump()}; PRODUCTS[pid]=row; audit('CREATE','PRODUCT',pid,row); persist_state(); return row
@app.get('/api/validate-gstin/{gstin}')
def validate_gstin(gstin:str):
    valid=len(gstin)==15 and gstin[:2].isdigit() and gstin[:2] in STATE_CODES
    return {'gstin':gstin,'valid':valid,'state_code':gstin[:2] if valid else None,'state':STATE_CODES.get(gstin[:2]) if valid else None}
@app.post('/api/invoices/calculate')
def calc(req:InvoiceRequest):
    return {'invoice':req.model_dump(),'calculation':validate_invoice(req)}
@app.post('/api/invoices')
def create(req:InvoiceRequest,user=Depends(require_permission('create'))):
    company_scope(user,req.company_id)
    ensure_period_open(req.gstin_id, req.invoice_date)
    return invoice_row(req,validate_invoice(req))
@app.get('/api/invoices')
def list_invoices(company_id:str='demo-company', period:Optional[str]=None):
    vals=[x for x in INVOICES.values() if x['request'].get('company_id')==company_id]
    if period: vals=[x for x in vals if x['request']['invoice_date'][:7]==period]
    return vals
@app.get('/api/invoices/{invoice_id}')
def get_invoice(invoice_id:str):
    if invoice_id not in INVOICES: raise HTTPException(404,'Invoice not found')
    return INVOICES[invoice_id]
@app.delete('/api/invoices/{invoice_id}')
def delete_invoice(invoice_id:str,user=Depends(require_permission('edit'))):
    inv=INVOICES.get(invoice_id)
    if not inv: raise HTTPException(404,'Invoice not found')
    ensure_period_open(inv['request'].get('gstin_id','demo-gstin'), inv['request']['invoice_date'])
    inv['status']='CANCELLED'; audit('CANCEL','INVOICE',invoice_id,{'status':'CANCELLED'}); persist_state(); return inv

@app.post('/api/einvoice/mock')
def mock_einvoice(req:EinvoiceRequest,user=Depends(require_permission('edit'))):
    inv=INVOICES.get(req.invoice_id)
    if not inv: raise HTTPException(404,'Invoice not found')
    r=inv['request']; aato=COMPANIES.get(r.get('company_id'),{}).get('aato',0)
    if aato>=100000000:
        age=(date.today()-date.fromisoformat(r['invoice_date'][:10])).days
        if age>30: raise HTTPException(422,'IRP reporting window exceeded: AATO ₹10 crore or above requires reporting within 30 days of invoice date.')
    if inv['status'] not in ('APPROVED','EINVOICE_GENERATED'):
        raise HTTPException(409,'Invoice must pass maker-checker approval before e-invoice generation.')
    inv['einvoice']=MockIRPProvider().generate(inv); inv['status']='EINVOICE_GENERATED'; audit('GENERATE_MOCK_IRN','E_INVOICE',req.invoice_id,inv['einvoice'],company_id=r.get('company_id','demo-company'),user_id=user['sub']); persist_state(); return inv['einvoice']
@app.post('/api/einvoice/{invoice_id}/cancel')
def cancel_irn(invoice_id:str,user=Depends(require_permission('edit'))):
    inv=INVOICES.get(invoice_id)
    if not inv or 'einvoice' not in inv: raise HTTPException(404,'IRN not found')
    generated=datetime.fromisoformat(inv['einvoice']['irn_date'].replace('Z','+00:00'))
    if (datetime.now(timezone.utc)-generated).total_seconds()>24*3600:
        raise HTTPException(422,'Mock IRN cancellation window exceeded: cancellation is allowed only within 24 hours of IRN generation.')
    inv['einvoice']['status']='CANCELLED_MOCK'; inv['status']='IRN_CANCELLED'; audit('CANCEL_IRN','E_INVOICE',invoice_id,inv['einvoice']); persist_state(); return inv['einvoice']
@app.get('/api/einvoice/{invoice_id}/json')
def einvoice_json(invoice_id:str):
    inv=INVOICES.get(invoice_id)
    if not inv: raise HTTPException(404,'Invoice not found')
    r=inv['request']; c=inv['calculation']; return {'Version':'1.1','TranDtls':{'TaxSch':'GST','SupTyp':'B2B' if r.get('customer_gstin') else 'B2C'},'DocDtls':{'Typ':'INV','No':r['invoice_number'],'Dt':r['invoice_date'][:10]},'SellerDtls':{'Gstin':r['supplier_gstin']},'BuyerDtls':{'Gstin':r.get('customer_gstin') or ''},'ValDtls':{'AssVal':c['taxable_value'],'CgstVal':c['cgst'],'SgstVal':c['sgst'],'IgstVal':c['igst'],'TotInvVal':c['total']},'ItemList':c['lines']}

@app.post('/api/purchases')
def create_purchase(req:PurchaseRequest,user=Depends(require_permission('create'))):
    company_scope(user,req.company_id)
    pid=str(uuid.uuid4()); row={'id':pid,**req.model_dump()}; PURCHASES[pid]=row; audit('CREATE','PURCHASE',pid,row); persist_state(); return row
@app.get('/api/purchases')
def purchases(company_id:str='demo-company'): return [x for x in PURCHASES.values() if x['company_id']==company_id]
@app.post('/api/gstr2b/import')
def import_gstr2b(rows:list[GSTR2BRow],user=Depends(require_permission('create'))):
    imported=0
    for req in rows:
        key=f"{req.company_id}:{req.gstin_id}:{req.vendor_gstin}:{req.invoice_number}:{req.invoice_date}"
        PURCHASES_2B[key]={'id':key,**req.model_dump()}
        imported+=1
    audit('IMPORT','GSTR2B',str(uuid.uuid4()),{'rows':imported})
    persist_state()
    return {'imported':imported,'total_rows':len(PURCHASES_2B)}

@app.get('/api/gstr2b')
def gstr2b(company_id:str='demo-company',period:str='2026-09'):
    return [x for x in PURCHASES_2B.values() if x['company_id']==company_id and x['invoice_date'][:7]==period]

@app.get('/api/reconciliation')
def reconciliation(period:str='2026-09',company_id:str='demo-company'):
    sales=[x for x in INVOICES.values() if x['request'].get('company_id')==company_id and x['request']['invoice_date'][:7]==period]
    result=[]
    for x in sales:
        e=x.get('einvoice'); result.append({'invoice_id':x['id'],'invoice_no':x['request']['invoice_number'],'invoice_total':x['calculation']['total'],'irn_status':e['status'] if e else 'MISSING_IRN','bucket':'OK' if e and e['status']=='GENERATED_MOCK' else 'Missing IRN'})
    purchases=[x for x in PURCHASES.values() if x['company_id']==company_id and x['invoice_date'][:7]==period]
    for p in purchases:
        matches=[x for x in PURCHASES_2B.values() if x['company_id']==company_id and x['vendor_gstin']==(p.get('vendor_gstin') or '') and x['invoice_number']==p['invoice_number']]
        if not matches: result.append({'purchase_id':p['id'],'invoice_no':p['invoice_number'],'book_total':p['total'],'gstr2b_status':'MISSING','bucket':'Missing in GSTR-2B'})
        else:
            m=matches[0]; same=abs(float(m['total'])-float(p['total']))<0.01
            result.append({'purchase_id':p['id'],'invoice_no':p['invoice_number'],'book_total':p['total'],'gstr2b_status':'MATCHED' if same else 'VALUE_MISMATCH','bucket':'OK' if same else 'Value mismatch'})
    return {'period':period,'rows':result,'summary':{'ok':sum(r['bucket']=='OK' for r in result),'exceptions':sum(r['bucket']!='OK' for r in result)}}

def gstr1_data(period, company_id):
    docs=[]; hsn={}; b2cs=[]; cdnr=[]
    for inv in INVOICES.values():
        r=inv['request']; c=inv['calculation']
        if r.get('company_id')!=company_id or r['invoice_date'][:7]!=period or inv['status']=='CANCELLED': continue
        sign=-1 if r['invoice_type']=='CREDIT_NOTE' else 1
        doc={'invoice_no':r['invoice_number'],'invoice_date':r['invoice_date'],'customer_gstin':r.get('customer_gstin'),'place_of_supply':r['place_of_supply'],'taxable_value':str(Decimal(str(c['taxable_value']))*sign),'igst':str(Decimal(str(c['igst']))*sign),'cgst':str(Decimal(str(c['cgst']))*sign),'sgst':str(Decimal(str(c['sgst']))*sign),'total':str(Decimal(str(c['total']))*sign),'reverse_charge':r['reverse_charge']}
        if r['invoice_type'] in ('CREDIT_NOTE','DEBIT_NOTE'): cdnr.append(doc)
        elif r.get('customer_gstin'): docs.append(doc)
        else: b2cs.append(doc)
        for line in c['lines']:
            key=line['hsn_sac']; x=hsn.setdefault(key,{'hsn_sac':key,'description':line['description'],'qty':0,'taxable_value':Decimal('0'),'igst':Decimal('0'),'cgst':Decimal('0'),'sgst':Decimal('0')})
            x['qty']+=line['qty']*sign; x['taxable_value']+=Decimal(str(line['taxable_value']))*sign; x['igst']+=Decimal(str(line['igst']))*sign; x['cgst']+=Decimal(str(line['cgst']))*sign; x['sgst']+=Decimal(str(line['sgst']))*sign
    def clean(v):
        if isinstance(v,Decimal): return str(v.quantize(Decimal('0.01')))
        return v
    return {'period':period,'b2b':docs,'b2c':b2cs,'cdnr':cdnr,'hsn_summary':[{k:clean(v) for k,v in x.items()} for x in hsn.values()]}

@app.get('/api/returns/gstr1/draft')
def gstr1(period:str='2026-09',company_id:str='demo-company'):
    d=gstr1_data(period,company_id); d.update({'status':'DRAFT','filing_ready':False,'schema_version':'GSTR1-DRAFT-v1','tables':{'4A_B2B':len(d['b2b']),'5_B2CL':0,'7_B2CS':len(d['b2c']),'9B_CDNR':len(d['cdnr']),'12_HSN':len(d['hsn_summary'])},'gstn_payload':{'gstin':next((g['gstin'] for g in GSTINS.values() if g['company_id']==company_id),'') ,'fp':period.replace('-',''),'b2b':d['b2b'],'b2cs':d['b2c'],'cdnr':d['cdnr'],'hsn':d['hsn_summary']}}); return d
@app.get('/api/returns/gstr3b/draft')
def gstr3b(period:str='2026-09',company_id:str='demo-company'):
    d=gstr1_data(period,company_id); out={'taxable':Decimal('0'),'cgst':Decimal('0'),'sgst':Decimal('0'),'igst':Decimal('0')}
    for doc in d['b2b']+d['b2c']+d['cdnr']:
        for k in out: out[k]+=Decimal(str(doc['taxable_value'] if k=='taxable' else doc[k]))
    purchases=[p for p in PURCHASES.values() if p['company_id']==company_id and p['invoice_date'][:7]==period and p['itc_eligible']]
    itc={k:sum(Decimal(str(p[k])) for p in purchases) for k in ('cgst','sgst','igst')}
    outward={k:str(v.quantize(Decimal('0.01'))) for k,v in out.items()}; available={k:str(v.quantize(Decimal('0.01'))) for k,v in itc.items()}; net={k:str((out[k]-itc[k]).quantize(Decimal('0.01'))) for k in ('cgst','sgst','igst')}
    return {'period':period,'status':'DRAFT','schema_version':'GSTR3B-DRAFT-v1','outward_supplies':outward,'itc_available':available,'net_tax_liability':net,'tables':{'3_1':{'taxable_outward':outward['taxable'],'cgst':outward['cgst'],'sgst':outward['sgst'],'igst':outward['igst']},'4A_ITC':available,'5_NET_TAX':net}}
class ApprovalRequest(BaseModel):
    invoice_id:str; decision:str; comment:str=''

@app.post('/api/invoices/{invoice_id}/submit')
def submit_invoice(invoice_id:str,user=Depends(require_permission('edit'))):
    inv=INVOICES.get(invoice_id)
    if not inv: raise HTTPException(404,'Invoice not found')
    inv['status']='PENDING_APPROVAL'; approval={'id':str(uuid.uuid4()),'invoice_id':invoice_id,'status':'PENDING','submitted_by':user['sub'],'submitted_at':datetime.now(timezone.utc).isoformat()}
    APPROVALS[invoice_id]=approval; audit('SUBMIT_APPROVAL','INVOICE',invoice_id,approval,company_id=inv['request']['company_id'],user_id=user['sub']); persist_state(); return approval

@app.post('/api/invoices/{invoice_id}/approve')
def approve_invoice(invoice_id:str,req:ApprovalRequest,user=Depends(require_permission('approve'))):
    inv=INVOICES.get(invoice_id)
    if not inv: raise HTTPException(404,'Invoice not found')
    if APPROVALS.get(invoice_id,{}).get('status')!='PENDING': raise HTTPException(409,'Invoice is not pending approval')
    if APPROVALS[invoice_id].get('submitted_by')==user['sub']: raise HTTPException(409,'Maker-checker control: the submitting user cannot approve the same invoice.')
    if req.decision not in ('APPROVE','REJECT'): raise HTTPException(422,'Decision must be APPROVE or REJECT')
    inv['status']='APPROVED' if req.decision=='APPROVE' else 'REJECTED'; approval=APPROVALS[invoice_id]; approval.update({'status':req.decision,'comment':req.comment,'approved_by':user['sub'],'approved_at':datetime.now(timezone.utc).isoformat()}); audit(req.decision,'INVOICE',invoice_id,approval,company_id=inv['request']['company_id'],user_id=user['sub']); persist_state(); return approval

@app.get('/api/approvals')
def approvals(company_id:str='demo-company',user=Depends(require_permission('read'))):
    company_scope(user,company_id); return [x for x in APPROVALS.values() if INVOICES.get(x['invoice_id'],{}).get('request',{}).get('company_id')==company_id]

@app.post('/api/returns/lock')
def lock_return(req:ReturnLockRequest,user=Depends(require_permission('lock'))):
    company_scope(user,GSTINS.get(req.gstin_id,{}).get('company_id',''))
    key=f"{req.gstin_id}:{req.return_type}:{req.period}"; RETURNS[key]={'id':str(uuid.uuid4()),**req.model_dump(),'status':'LOCKED','locked_at':datetime.now(timezone.utc).isoformat()}; audit('LOCK_RETURN','RETURN_PERIOD',RETURNS[key]['id'],RETURNS[key],company_id=GSTINS.get(req.gstin_id,{}).get('company_id','demo-company'),user_id=user['sub']); persist_state(); return RETURNS[key]
@app.get('/api/returns')
def returns(gstin_id:str='demo-gstin'): return [x for x in RETURNS.values() if x['gstin_id']==gstin_id]
@app.get('/api/audit-verify')
def audit_verify(company_id:str='demo-company'):
    rows=[x for x in AUDIT if x['company_id']==company_id]; previous='GENESIS'
    for x in rows:
        payload={k:x[k] for k in ('action','entity_type','entity_id','old_value','new_value','company_id','user_id','created_at','previous_hash')}
        expected=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
        if x.get('previous_hash')!=previous or x.get('hash')!=expected:
            return {'valid':False,'checked':len(rows),'failed_event':x['id']}
        previous=x['hash']
    return {'valid':True,'checked':len(rows),'head_hash':previous}

@app.get('/api/audit-logs')
def audit_logs(company_id:str='demo-company'): return [x for x in AUDIT if x['company_id']==company_id]

@app.get('/api/export/gstr1.csv')
def export_gstr1(period:str='2026-09',company_id:str='demo-company'):
    d=gstr1_data(period,company_id); s=io.StringIO(); w=csv.writer(s); w.writerow(['Table','Invoice No','Date','GSTIN','POS','Taxable','CGST','SGST','IGST','Total'])
    for table,key in [('4A_B2B','b2b'),('7_B2CS','b2c'),('9B_CDNR','cdnr')]:
        for x in d[key]: w.writerow([table,x['invoice_no'],x['invoice_date'],x.get('customer_gstin') or '',x['place_of_supply'],x['taxable_value'],x['cgst'],x['sgst'],x['igst'],x['total']])
    return StreamingResponse(iter([s.getvalue()]),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename=gstr1-{period}.csv'})

@app.post('/api/auth/login')
def login(req:AuthRequest):
    u=next((x for x in USERS.values() if x['email']==req.email),None)
    if not u or not verify_password(req.password,u.get('password_hash','')): raise HTTPException(401,'Invalid credentials')
    token=make_token(u)
    return {'access_token':token,'token_type':'bearer','user':{k:v for k,v in u.items() if k!='password_hash'},'permissions':sorted(ROLES.get(u['role'],set()))}

@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    u=USERS.get(user['sub'])
    if not u: raise HTTPException(401,'User not found')
    return {**{k:v for k,v in u.items() if k!='password_hash'},'permissions':sorted(ROLES.get(u['role'],set()))}

@app.get('/api/users')
def users(company_id:str='demo-company', user=Depends(require_permission('admin'))):
    company_scope(user,company_id); return [{k:v for k,v in x.items() if k!='password_hash'} for x in USERS.values() if x['company_id']==company_id]

class UserRequest(BaseModel):
    company_id:str='demo-company'; name:str; email:str; role:str='ACCOUNTANT'; password:str=Field(min_length=8)

@app.post('/api/users')
def create_user(req:UserRequest,user=Depends(require_permission('admin'))):
    company_scope(user,req.company_id)
    if req.role not in ROLES: raise HTTPException(422,'Invalid role')
    if any(x['email']==req.email for x in USERS.values()): raise HTTPException(409,'Email already exists')
    uid=str(uuid.uuid4()); row={'id':uid,'company_id':req.company_id,'name':req.name,'email':req.email,'role':req.role,'password_hash':hash_password(req.password)}
    USERS[uid]=row; audit('CREATE','USER',uid,{k:v for k,v in row.items() if k!='password_hash'},company_id=req.company_id,user_id=user['sub']); persist_state()
    return {k:v for k,v in row.items() if k!='password_hash'}

@app.get('/api/dashboard')
def dashboard(period:str='2026-09',company_id:str='demo-company'):
    sales=[x for x in INVOICES.values() if x['request'].get('company_id')==company_id and x['request']['invoice_date'][:7]==period and x['status']!='CANCELLED']
    taxable=sum(Decimal(str(x['calculation']['taxable_value'])) for x in sales); tax=sum(Decimal(str(x['calculation']['cgst']))+Decimal(str(x['calculation']['sgst']))+Decimal(str(x['calculation']['igst'])) for x in sales)
    purchases=[x for x in PURCHASES.values() if x['company_id']==company_id and x['invoice_date'][:7]==period]
    itc=sum(Decimal(str(x['cgst']))+Decimal(str(x['sgst']))+Decimal(str(x['igst'])) for x in purchases if x['itc_eligible'])
    aato=COMPANIES.get(company_id,{}).get('aato',0)
    return {'period':period,'invoice_count':len(sales),'taxable_sales':str(taxable),'output_tax':str(tax),'itc_available':str(itc),'net_tax':str(tax-itc),'aato':aato,'e_invoice_applicable':aato>=50000000,'e_invoice_30day_rule':aato>=100000000,'gstr1_status':next((x['status'] for x in RETURNS.values() if x['gstin_id']=='demo-gstin' and x['return_type']=='GSTR1' and x['period']==period),'DRAFT'),'gstr3b_status':next((x['status'] for x in RETURNS.values() if x['gstin_id']=='demo-gstin' and x['return_type']=='GSTR3B' and x['period']==period),'DRAFT')}

@app.get('/api/invoices/{invoice_id}/pdf')
def invoice_pdf(invoice_id:str):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    inv=INVOICES.get(invoice_id)
    if not inv: raise HTTPException(404,'Invoice not found')
    buf=io.BytesIO(); c=canvas.Canvas(buf,pagesize=A4); w,h=A4; r=inv['request']; calc=inv['calculation']
    c.setFont('Helvetica-Bold',16); c.drawString(40,h-50,'SARO DEVI ENTERPRISES'); c.setFont('Helvetica',9); c.drawString(40,h-66,'GSTIN: '+r['supplier_gstin']); c.drawRightString(w-40,h-50,r['invoice_type'].replace('_',' '))
    y=h-105; c.setFont('Helvetica-Bold',10); c.drawString(40,y,'Invoice No: '+r['invoice_number']); c.drawString(300,y,'Date: '+r['invoice_date'][:10]); y-=28
    c.setFont('Helvetica',9); c.drawString(40,y,'Bill To: '+r['customer_name']); y-=15; c.drawString(40,y,'GSTIN: '+(r.get('customer_gstin') or 'Unregistered')); y-=30
    c.line(40,y,w-40,y); y-=18; c.setFont('Helvetica-Bold',8); c.drawString(40,y,'Description'); c.drawString(270,y,'Qty'); c.drawString(325,y,'Rate'); c.drawString(400,y,'Taxable'); c.drawString(485,y,'Total'); y-=14; c.setFont('Helvetica',8)
    for l in calc['lines']:
        c.drawString(40,y,str(l['description'])[:34]); c.drawRightString(300,y,str(l['qty'])); c.drawRightString(365,y,str(l['rate'])); c.drawRightString(455,y,str(l['taxable_value'])); c.drawRightString(w-40,y,str(l['total'])); y-=15
    y-=12; c.line(350,y,w-40,y); y-=18; c.drawRightString(w-120,y,'Taxable: ₹ '+str(calc['taxable_value'])); y-=14; c.drawRightString(w-120,y,'CGST: ₹ '+str(calc['cgst'])); y-=14; c.drawRightString(w-120,y,'SGST: ₹ '+str(calc['sgst'])); y-=14; c.drawRightString(w-120,y,'IGST: ₹ '+str(calc['igst'])); y-=18; c.setFont('Helvetica-Bold',11); c.drawRightString(w-40,y,'Grand Total: ₹ '+str(calc['total']))
    if 'einvoice' in inv: y-=35; c.setFont('Helvetica',8); c.drawString(40,y,'IRN: '+inv['einvoice']['irn']); c.drawString(40,y-12,'QR payload: '+inv['einvoice']['signed_qr_payload'])
    c.showPage(); c.save(); buf.seek(0); return Response(buf.getvalue(),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename={r["invoice_number"]}.pdf'})

@app.get('/api/export/invoices.xlsx')
def export_invoices_xlsx(period:str='2026-09',company_id:str='demo-company'):
    from openpyxl import Workbook
    wb=Workbook(); ws=wb.active; ws.title='Invoices'; ws.append(['Invoice No','Date','Customer','GSTIN','Taxable','CGST','SGST','IGST','Total','Status'])
    for x in INVOICES.values():
        r=x['request']; c=x['calculation']
        if r.get('company_id')==company_id and r['invoice_date'][:7]==period: ws.append([r['invoice_number'],r['invoice_date'],r['customer_name'],r.get('customer_gstin') or '',c['taxable_value'],c['cgst'],c['sgst'],c['igst'],c['total'],x['status']])
    buf=io.BytesIO(); wb.save(buf); buf.seek(0); return StreamingResponse(iter([buf.getvalue()]),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename=invoices-{period}.xlsx'})
