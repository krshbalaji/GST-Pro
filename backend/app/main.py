import csv, hashlib, io, json, os, uuid, copy
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional
import jwt
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from .gst import calculate_invoice, Scheme, hsn_min_digits, financial_year
from .storage import store, transaction
from .security import hash_password, verify_password, make_token, decode_token, ROLES
from .einvoice import MockIRPProvider
from .api import domain_router
from .repositories.factory import build_repositories
from .services import invoice_service, compliance_service

app=FastAPI(title='GST Pro API',version='1.4.0')
DEMO_MODE=os.getenv('GSTPRO_MODE','demo').lower()=='demo'
_cors=[x.strip() for x in os.getenv('CORS_ALLOWED_ORIGINS','http://localhost:3000').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=_cors,allow_methods=['*'],allow_headers=['*'],allow_credentials=True)
@app.get('/ready')
def ready():
    db=store.health()
    if db.get('enabled') and db.get('status')!='ok': return JSONResponse(status_code=503,content={'status':'not_ready','database':db})
    return {'status':'ready','mode':'demo' if DEMO_MODE else 'production','database':db}
app.include_router(domain_router)
RATE_PRESETS={'REGULAR_5':{'name':'5% Regular','scheme':'REGULAR','rate':5},'REGULAR_12':{'name':'12% Regular','scheme':'REGULAR','rate':12},'REGULAR_18':{'name':'18% Regular','scheme':'REGULAR','rate':18},'REGULAR_28':{'name':'28% Regular','scheme':'REGULAR','rate':28},'COMPOSITION_1':{'name':'1% Composition (configurable)','scheme':'COMPOSITION','rate':1},'COMPOSITION_5':{'name':'5% Composition (configurable)','scheme':'COMPOSITION','rate':5},'COMPOSITION_6':{'name':'6% Composition (configurable)','scheme':'COMPOSITION','rate':6},'EXEMPT':{'name':'Exempt / Nil-rated','scheme':'REGULAR','rate':0}}
STATE_CODES={'01':'Jammu & Kashmir','02':'Himachal Pradesh','03':'Punjab','04':'Chandigarh','05':'Uttarakhand','06':'Haryana','07':'Delhi','08':'Rajasthan','09':'Uttar Pradesh','10':'Bihar','11':'Sikkim','12':'Arunachal Pradesh','13':'Nagaland','14':'Manipur','15':'Mizoram','16':'Tripura','17':'Meghalaya','18':'Assam','19':'West Bengal','20':'Jharkhand','21':'Odisha','22':'Chhattisgarh','23':'Madhya Pradesh','24':'Gujarat','27':'Maharashtra','29':'Karnataka','30':'Goa','32':'Kerala','33':'Tamil Nadu','34':'Puducherry','35':'Andaman & Nicobar Islands','36':'Telangana','37':'Andhra Pradesh','38':'Ladakh','97':'Other Territory'}
COMPANIES={};GSTINS={};CUSTOMERS={};VENDORS={};PRODUCTS={};USERS={};INVOICES={};PURCHASES={};AUDIT=[];RETURNS={};APPROVALS={};PURCHASES_2B={};REPOSITORIES=None
SECRET=os.getenv('JWT_SECRET','gst-pro-production-secret-change-me-please-set-env')
class Line(BaseModel):
    model_config=ConfigDict(extra='forbid')
    product_id:str|None=None;description:str;hsn_sac:str;unit:str;qty:float=Field(gt=0);rate:float=Field(ge=0);gst_rate:float=Field(ge=0);taxable:bool=True
class InvoiceRequest(BaseModel):
    invoice_type:str='TAX_INVOICE';scheme:Scheme=Scheme.REGULAR;supplier_state_code:str;place_of_supply:str;supplier_gstin:str;customer_gstin:str|None=None;customer_name:str;customer_state_code:str|None=None;invoice_date:str;series:str='SDE';invoice_number:str;lines:list[Line]=Field(min_length=1);reverse_charge:bool=False;company_id:str='demo-company';gstin_id:str='demo-gstin';notes:str=''
class PartyRequest(BaseModel):
    company_id:str='demo-company';name:str;gstin:str|None=None;state_code:str|None=None;address:dict={};pan:str|None=None
class ProductRequest(BaseModel):
    company_id:str='demo-company';description:str;hsn_sac:str;unit:str;rate:float=Field(ge=0);gst_rate:float=Field(ge=0);is_service:bool=False;active:bool=True
class PurchaseRequest(BaseModel):
    company_id:str='demo-company';gstin_id:str='demo-gstin';vendor_name:str;vendor_gstin:str|None=None;invoice_number:str;invoice_date:str;taxable_value:float;cgst:float=0;sgst:float=0;igst:float=0;total:float;source:str='MANUAL';itc_eligible:bool=True
class GSTR2BRow(BaseModel):
    company_id:str='demo-company';gstin_id:str='demo-gstin';vendor_gstin:str;vendor_name:str='';invoice_number:str;invoice_date:str;taxable_value:float;cgst:float=0;sgst:float=0;igst:float=0;total:float=0
class AuthRequest(BaseModel): email:str;password:str
class EinvoiceRequest(BaseModel): invoice_id:str
class ReturnLockRequest(BaseModel): gstin_id:str='demo-gstin';return_type:str;period:str

def _canonical_company_id(company_id):
    if DEMO_MODE:return company_id
    return str(REPOSITORIES['invoices'].mapper.resolve('company',company_id))
def _canonical_gstin_id(gstin_id):
    if DEMO_MODE:return gstin_id
    return str(REPOSITORIES['invoices'].mapper.resolve('gstin',gstin_id))
def _canonical_user_id(user_id):
    if DEMO_MODE:return user_id
    return str(REPOSITORIES['invoices'].mapper.resolve('user',user_id))

def audit(action,entity_type,entity_id,new=None,old=None,company_id='demo-company',user_id=None):
    previous=AUDIT[-1].get('hash',AUDIT[-1].get('event_hash')) if AUDIT else 'GENESIS'
    payload={'action':action,'entity_type':entity_type,'entity_id':entity_id,'old_value':copy.deepcopy(old),'new_value':copy.deepcopy(new),'company_id':company_id,'user_id':user_id,'created_at':datetime.now(timezone.utc).isoformat(),'previous_hash':previous}
    payload['hash']=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
    event={'id':str(uuid.uuid4()),**payload}
    if REPOSITORIES is not None and not DEMO_MODE:REPOSITORIES['audit'].append(event)
    else:AUDIT.append(event)
def persist_state():return
def seed():
    if COMPANIES:return
    COMPANIES['demo-company']={'id':'demo-company','legal_name':'SARO DEVI ENTERPRISES','trade_name':'Saro Devi Enterprises','pan':'ABCDE1234F','address':{'line1':'123, North Veli Street','city':'Madurai','state':'Tamil Nadu','pincode':'625001'},'aato':45000000}
    GSTINS['demo-gstin']={'id':'demo-gstin','company_id':'demo-company','gstin':'33ABCDE1234F1Z5','state_code':'33','scheme':'REGULAR','legal_name':'SARO DEVI ENTERPRISES','trade_name':'Saro Devi Enterprises','aato':45000000,'e_invoice_enabled':True}
    CUSTOMERS['C1']={'id':'C1','company_id':'demo-company','name':'ABC Traders','gstin':'33AACFA1234A1Z1','state_code':'33','address':{'line1':'123, Anna Salai','city':'Chennai','state':'Tamil Nadu','pincode':'600002'}}
    PRODUCTS.update({'P1':{'id':'P1','company_id':'demo-company','description':'Cotton Shirt (Men)','hsn_sac':'620520','unit':'PCS','rate':500,'gst_rate':18,'is_service':False,'active':True},'P2':{'id':'P2','company_id':'demo-company','description':'Towel (Home Textile)','hsn_sac':'630260','unit':'PCS','rate':300,'gst_rate':12,'is_service':False,'active':True},'P3':{'id':'P3','company_id':'demo-company','description':'IT Consulting','hsn_sac':'998313','unit':'HRS','rate':2500,'gst_rate':18,'is_service':True,'active':True}})
    USERS['U1']={'id':'U1','company_id':'demo-company','name':'Admin','email':'admin@gstpro.local','role':'OWNER','password_hash':hash_password('admin')}
    USERS['U2']={'id':'U2','company_id':'demo-company','name':'Demo CA','email':'ca@gstpro.local','role':'CA','password_hash':hash_password('caadmin123')}
if DEMO_MODE:seed()
else:
    from .repositories.production_state import ProductionState
    REPOSITORIES=build_repositories();s=ProductionState(REPOSITORIES);COMPANIES=s.companies;GSTINS=s.gstins;CUSTOMERS=s.customers;VENDORS=s.vendors;PRODUCTS=s.products;USERS=s.users;INVOICES=s.invoices;PURCHASES=s.purchases;PURCHASES_2B=s.purchases_2b;AUDIT=s.audit;RETURNS=s.returns;APPROVALS=s.approvals

def current_user(authorization:str=Header(default='')):
    if not authorization.startswith('Bearer '):raise HTTPException(401,'Authentication required')
    try:return decode_token(authorization[7:])
    except Exception:raise HTTPException(401,'Invalid or expired access token')
def require_permission(permission:str):
    def dep(user=Depends(current_user)):
        if permission not in ROLES.get(user.get('role'),set()):raise HTTPException(403,f'Role {user.get("role")} cannot perform {permission}')
        return user
    return dep
def company_scope(user,company_id):
    if DEMO_MODE:
        if user.get('company_id')!=company_id:raise HTTPException(403,'Cross-company access denied')
        return
    try:
        if _canonical_company_id(company_id)!=_canonical_company_id(user.get('company_id')):raise HTTPException(403,'Cross-company access denied')
    except (ValueError,TypeError):raise HTTPException(403,'Cross-company access denied')

def ensure_period_open(gstin_id,invoice_date):
    try:compliance_service.ensure_period_open(REPOSITORIES['returns'].list_by_gstin(gstin_id) if REPOSITORIES is not None and not DEMO_MODE else RETURNS.values(),gstin_id,invoice_date)
    except ValueError as exc:raise HTTPException(409,str(exc))
def validate_invoice(req):
    if req.invoice_type=='TAX_INVOICE' and req.scheme==Scheme.COMPOSITION:raise HTTPException(422,'Composition taxpayers must issue a Bill of Supply; GST must not be charged to the customer.')
    if not DEMO_MODE:
        try:
            gstin=GSTINS.get(req.gstin_id)
            if not gstin or _canonical_company_id(gstin.get('company_id'))!=_canonical_company_id(req.company_id):raise HTTPException(422,'GSTIN does not belong to the selected company.')
            if gstin.get('gstin') and req.supplier_gstin!=gstin['gstin']:raise HTTPException(422,'Supplier GSTIN does not match the selected GSTIN.')
        except (ValueError,TypeError):raise HTTPException(422,'GSTIN or company identifier is invalid.')
    if req.scheme==Scheme.COMPOSITION and req.invoice_type not in ('BILL_OF_SUPPLY','CREDIT_NOTE','DEBIT_NOTE'):raise HTTPException(422,'Composition supply requires Bill of Supply.')
    if len(req.supplier_gstin)!=15:raise HTTPException(422,'Supplier GSTIN must be 15 characters.')
    if req.supplier_gstin[:2]!=req.supplier_state_code:raise HTTPException(422,'Supplier state code does not match GSTIN.')
    for l in req.lines:
        try:invoice_service.validate_hsn(l.hsn_sac,COMPANIES.get(req.company_id,{}).get('aato',0))
        except ValueError as exc:raise HTTPException(422,str(exc))
    return invoice_service.calculate([x.model_dump() for x in req.lines],req.scheme,req.supplier_state_code,req.place_of_supply)
def invoice_row(req,calc,status='DRAFT'):
    iid=str(uuid.uuid4());row={'id':iid,'created_at':datetime.now(timezone.utc).isoformat(),'request':req.model_dump(),'calculation':{k:str(v) if isinstance(v,Decimal) else v for k,v in calc.items()},'status':status}
    try:
        if REPOSITORIES is not None and not DEMO_MODE:
            with transaction() as conn:
                row=REPOSITORIES['invoices'].create(row,conn=conn);REPOSITORIES['audit'].append({'id':str(uuid.uuid4()),'action':'CREATE','entity_type':'INVOICE','entity_id':row['id'],'new_value':row,'company_id':req.company_id,'user_id':None,'created_at':datetime.now(timezone.utc).isoformat(),'previous_hash':'GENESIS','hash':''},conn=conn)
        else:INVOICES[iid]=row;audit('CREATE','INVOICE',iid,row,company_id=req.company_id)
    except Exception as exc:raise HTTPException(409,f'Invoice could not be persisted: {exc}')
    return row

@app.get('/api/products')
def products(company_id='demo-company',user=Depends(require_permission('read'))):
    company_scope(user,company_id);canonical=_canonical_company_id(company_id)
    if REPOSITORIES is not None and not DEMO_MODE:return REPOSITORIES['masters'].list_by_company('products',canonical)
    return [x for x in PRODUCTS.values() if _canonical_company_id(x['company_id'])==canonical and x.get('active',True)]

@app.get('/api/gstins')
def gstins(company_id='demo-company',user=Depends(require_permission('read'))):
    company_scope(user,company_id);canonical=_canonical_company_id(company_id)
    if REPOSITORIES is not None and not DEMO_MODE:return REPOSITORIES['masters'].list_by_company('gstins',canonical)
    return [x for x in GSTINS.values() if _canonical_company_id(x['company_id'])==canonical]

@app.get('/api/customers')
def customers(company_id='demo-company',user=Depends(require_permission('read'))):
    company_scope(user,company_id);canonical=_canonical_company_id(company_id)
    if REPOSITORIES is not None and not DEMO_MODE:return REPOSITORIES['masters'].list_by_company('customers',canonical)
    return [x for x in CUSTOMERS.values() if _canonical_company_id(x['company_id'])==canonical]

@app.get('/api/vendors')
def vendors(company_id='demo-company',user=Depends(require_permission('read'))):
    company_scope(user,company_id);canonical=_canonical_company_id(company_id)
    if REPOSITORIES is not None and not DEMO_MODE:return REPOSITORIES['masters'].list_by_company('vendors',canonical)
    return [x for x in VENDORS.values() if _canonical_company_id(x['company_id'])==canonical]

@app.post('/api/invoices/calculate')
def calc(req:InvoiceRequest):return {'invoice':req.model_dump(),'calculation':validate_invoice(req)}
@app.post('/api/invoices')
def create(req:InvoiceRequest,user=Depends(require_permission('create'))):company_scope(user,req.company_id);ensure_period_open(req.gstin_id,req.invoice_date);return invoice_row(req,validate_invoice(req))
@app.get('/api/invoices')
def list_invoices(company_id='demo-company',period:Optional[str]=None,user=Depends(require_permission('read'))):
    company_scope(user,company_id);return REPOSITORIES['invoices'].list_by_company(company_id,period) if REPOSITORIES is not None and not DEMO_MODE else [x for x in INVOICES.values() if x['request'].get('company_id')==company_id and (not period or x['request']['invoice_date'][:7]==period)]
@app.get('/api/invoices/{invoice_id}')
def get_invoice(invoice_id,user=Depends(require_permission('read'))):
    inv=REPOSITORIES['invoices'].get(invoice_id) if REPOSITORIES is not None and not DEMO_MODE else INVOICES.get(invoice_id)
    if not inv:raise HTTPException(404,'Invoice not found')
    company_scope(user,inv['request'].get('company_id',''));return inv

@app.post('/api/returns/lock')
def lock_return(req:ReturnLockRequest,user=Depends(require_permission('lock'))):
    try:
        gstin=GSTINS.get(req.gstin_id)
        if not gstin:raise ValueError
        company_id=gstin.get('company_id','')
        company_scope(user,company_id)
    except ValueError:raise HTTPException(422,'Invalid GSTIN identifier')
    if REPOSITORIES is not None and not DEMO_MODE:return REPOSITORIES['returns'].save({'id':str(uuid.uuid4()),'gstin_id':req.gstin_id,'return_type':req.return_type,'period':req.period,'status':'LOCKED','filed_on':None,'json_file':{}})
    key=f'{req.gstin_id}:{req.return_type}:{req.period}';RETURNS[key]={'id':str(uuid.uuid4()),**req.model_dump(),'status':'LOCKED'};return RETURNS[key]

@app.get('/api/purchases')
def purchases(company_id='demo-company',user=Depends(require_permission('read'))):
    company_scope(user,company_id);return REPOSITORIES['purchases'].list_by_company(company_id) if REPOSITORIES is not None and not DEMO_MODE else [x for x in PURCHASES.values() if x['company_id']==company_id]
@app.post('/api/purchases')
def create_purchase(req:PurchaseRequest,user=Depends(require_permission('create'))):
    company_scope(user,req.company_id)
    if REPOSITORIES is not None and not DEMO_MODE:
        pid=str(uuid.uuid4());row={**req.model_dump(),'id':pid}
        with transaction() as conn:REPOSITORIES['purchases'].create(row,conn=conn);REPOSITORIES['audit'].append({'id':str(uuid.uuid4()),'action':'CREATE','entity_type':'PURCHASE','entity_id':pid,'new_value':row,'company_id':req.company_id,'user_id':user['sub'],'created_at':datetime.now(timezone.utc).isoformat(),'previous_hash':'GENESIS','hash':''},conn=conn)
        return row
    pid=str(uuid.uuid4());row={'id':pid,**req.model_dump()};PURCHASES[pid]=row;return row

@app.post('/api/gstr2b/import')
def import_gstr2b(rows:list[GSTR2BRow],user=Depends(require_permission('create'))):
    for req in rows:
        company_scope(user,req.company_id)
        if REPOSITORIES is not None and not DEMO_MODE:REPOSITORIES['reconciliation'].upsert_2b(req.model_dump())
        else:PURCHASES_2B[f'{req.company_id}:{req.gstin_id}:{req.vendor_gstin}:{req.invoice_number}:{req.invoice_date}']={'id':f'{req.company_id}:{req.gstin_id}:{req.vendor_gstin}:{req.invoice_number}:{req.invoice_date}',**req.model_dump()}
    return {'imported':len(rows),'total_rows':len(PURCHASES_2B)}

@app.get('/api/reconciliation')
def reconciliation(period='2026-09',company_id='demo-company',user=Depends(require_permission('read'))):
    company_scope(user,company_id)
    if REPOSITORIES is not None and not DEMO_MODE:
        purchases=REPOSITORIES['purchases'].list_by_company(company_id,period);entries=REPOSITORIES['reconciliation'].list_2b(company_id,period);result=[]
        for p in purchases:
            matches=[x for x in entries if x.get('vendor_gstin')==(p.get('vendor_gstin') or '') and x.get('invoice_number')==p.get('invoice_number')]
            if not matches:result.append({'purchase_id':str(p['id']),'invoice_no':p['invoice_number'],'book_total':str(p['total']),'gstr2b_status':'MISSING','bucket':'Missing in GSTR-2B'})
            else:
                m=matches[0];same=abs(float(m['total'])-float(p['total']))<0.01;result.append({'purchase_id':str(p['id']),'invoice_no':p['invoice_number'],'book_total':str(p['total']),'gstr2b_status':'MATCHED' if same else 'VALUE_MISMATCH','bucket':'OK' if same else 'Value mismatch'})
        return {'period':period,'rows':result,'summary':{'ok':sum(r['bucket']=='OK' for r in result),'exceptions':sum(r['bucket']!='OK' for r in result)}}
    return {'period':period,'rows':[],'summary':{'ok':0,'exceptions':0}}

class ApprovalRequest(BaseModel):invoice_id:str;decision:str;comment:str=''
@app.post('/api/invoices/{invoice_id}/submit')
def submit_invoice(invoice_id,user=Depends(require_permission('edit'))):
    inv=REPOSITORIES['invoices'].get(invoice_id) if REPOSITORIES is not None and not DEMO_MODE else INVOICES.get(invoice_id)
    if not inv:raise HTTPException(404,'Invoice not found')
    company_scope(user,inv['request'].get('company_id',''));ensure_period_open(inv['request'].get('gstin_id',''),inv['request']['invoice_date'])
    approval={'id':str(uuid.uuid4()),'invoice_id':invoice_id,'status':'PENDING','submitted_by':user['sub'],'submitted_at':datetime.now(timezone.utc).isoformat()}
    try:
        if REPOSITORIES is not None and not DEMO_MODE:return REPOSITORIES['transactions'].submit_invoice(invoice_id,approval,{'id':str(uuid.uuid4()),'action':'SUBMIT_APPROVAL','entity_type':'INVOICE','entity_id':invoice_id,'new_value':approval,'company_id':inv['request']['company_id'],'user_id':user['sub'],'created_at':datetime.now(timezone.utc).isoformat(),'previous_hash':'GENESIS','hash':''})[1]
        inv['status']='PENDING_APPROVAL';APPROVALS[invoice_id]=approval;return approval
    except Exception as exc:raise HTTPException(409,f'Invoice approval submission failed: {exc}')
@app.post('/api/invoices/{invoice_id}/approve')
def approve_invoice(invoice_id,req:dict,user=Depends(require_permission('approve'))):
    inv=REPOSITORIES['invoices'].get(invoice_id) if REPOSITORIES is not None and not DEMO_MODE else INVOICES.get(invoice_id)
    if not inv:raise HTTPException(404,'Invoice not found')
    company_scope(user,inv['request'].get('company_id',''))
    approval=REPOSITORIES['approvals'].get(invoice_id) if REPOSITORIES is not None and not DEMO_MODE else APPROVALS.get(invoice_id)
    if not approval or approval.get('status')!='PENDING':raise HTTPException(409,'Invoice approval is not pending')
    if _canonical_user_id(approval.get('submitted_by'))==_canonical_user_id(user['sub']):raise HTTPException(409,'Maker-checker control: the submitting user cannot approve the same invoice.')
    if req.get('decision') not in ('APPROVE','REJECT'):raise HTTPException(422,'Decision must be APPROVE or REJECT')
    target='APPROVED' if req['decision']=='APPROVE' else 'REJECTED';approval={**approval,'status':req['decision'],'comment':req.get('comment',''),'approved_by':user['sub'],'approved_at':datetime.now(timezone.utc).isoformat()}
    try:
        if REPOSITORIES is not None and not DEMO_MODE:return REPOSITORIES['transactions'].decide_invoice(invoice_id,approval,{'id':str(uuid.uuid4()),'action':req['decision'],'entity_type':'INVOICE','entity_id':invoice_id,'old_value':{'status':'PENDING_APPROVAL'},'new_value':approval,'company_id':inv['request']['company_id'],'user_id':user['sub'],'created_at':datetime.now(timezone.utc).isoformat(),'previous_hash':'GENESIS','hash':''},target)[1]
        inv['status']=target;APPROVALS[invoice_id]=approval;return approval
    except Exception as exc:raise HTTPException(409,f'Invoice approval failed: {exc}')
@app.post('/api/einvoice/mock')
def mock_einvoice(req:EinvoiceRequest,user=Depends(require_permission('edit'))):
    inv=REPOSITORIES['invoices'].get(req.invoice_id) if REPOSITORIES is not None and not DEMO_MODE else INVOICES.get(req.invoice_id)
    if not inv:raise HTTPException(404,'Invoice not found')
    if inv['status'] not in ('APPROVED','EINVOICE_GENERATED'):raise HTTPException(409,'Invoice must pass maker-checker approval before e-invoice generation.')
    return MockIRPProvider().generate(inv)

@app.get('/api/audit-verify')
def audit_verify(company_id='demo-company',user=Depends(require_permission('read'))):
    company_scope(user,company_id)
    rows=REPOSITORIES['audit'].list_by_company(company_id) if REPOSITORIES is not None and not DEMO_MODE else [x for x in AUDIT if x['company_id']==company_id]
    previous='GENESIS'
    for x in rows:
        payload={k:x[k] for k in ('action','entity_type','entity_id','old_value','new_value','company_id','user_id','created_at','previous_hash')}
        expected=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
        if x.get('previous_hash')!=previous or x.get('hash')!=expected:return {'valid':False,'checked':len(rows),'failed_event':x['id']}
        previous=x['hash']
    return {'valid':True,'checked':len(rows),'head_hash':previous}

@app.post('/api/auth/login')
def login(req:AuthRequest):
    u=REPOSITORIES['masters'].get_user_by_email(req.email) if REPOSITORIES is not None and not DEMO_MODE else next((x for x in USERS.values() if x['email']==req.email),None)
    if not u or not verify_password(req.password,u.get('password_hash','')) or u.get('is_active',True) is False:raise HTTPException(401,'Invalid credentials')
    return {'access_token':make_token(u),'token_type':'bearer','user':{k:v for k,v in u.items() if k!='password_hash'},'permissions':sorted(ROLES.get(u['role'],set()))}
