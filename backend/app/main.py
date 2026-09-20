import csv, hashlib, io, json, os, uuid, copy
from decimal import Decimal
from typing import Optional
import jwt
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from .gst import calculate_invoice, Scheme, hsn_min_digits, financial_year
from .storage import store
from .security import hash_password, verify_password, make_token, decode_token, ROLES
from .einvoice import MockIRPProvider
from .api import domain_router
from .services import invoice_service, compliance_service

app=FastAPI(title='GST Pro API', version='1.4.0')
DEMO_MODE = os.getenv('GSTPRO_MODE','demo').lower() == 'demo'
_cors = [x.strip() for x in os.getenv('CORS_ALLOWED_ORIGINS','http://localhost:3000').split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_cors, allow_methods=['*'], allow_headers=['*'], allow_credentials=True)

@app.get('/ready')
def ready():
    db=store.health()
    if db.get('enabled') and db.get('status')!='ok':
        return JSONResponse(status_code=503, content={'status':'not_ready','database':db})
    return {'status':'ready','mode':'demo' if DEMO_MODE else 'production','database':db}

app.include_router(domain_router)

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

# Demo repository: Python dictionaries are intentionally the active datastore for development/testing.
# Production persistence is tracked separately and must not silently fall back to process memory.
COMPANIES={}; GSTINS={}; CUSTOMERS={}; VENDORS={}; PRODUCTS={}; USERS={}; INVOICES={}; PURCHASES={}; AUDIT=[]; RETURNS={}; APPROVALS={}