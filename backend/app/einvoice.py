from abc import ABC, abstractmethod
import hashlib, uuid
from .gst import financial_year

class EInvoiceProvider(ABC):
    @abstractmethod
    def generate(self, invoice:dict)->dict: ...
    @abstractmethod
    def cancel(self, invoice:dict)->dict: ...

class MockIRPProvider(EInvoiceProvider):
    def generate(self, invoice):
        r=invoice['request']
        raw=f"{r['supplier_gstin']}|{financial_year(r['invoice_date'])}|{'INV' if r['invoice_type']=='TAX_INVOICE' else 'CRN' if r['invoice_type']=='CREDIT_NOTE' else 'DBN'}|{r['invoice_number']}".encode()
        irn=hashlib.sha256(raw).hexdigest()
        return {'status':'GENERATED_MOCK','irn':irn,'irn_date':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'ack_no':str(uuid.uuid4().int)[:15],'signed_qr_payload':f'MOCK|{irn}','schema':'GST INV-01 mock'}
    def cancel(self, invoice):
        return {'status':'CANCELLED_MOCK'}

class GSPIRPProvider(EInvoiceProvider):
    """Adapter contract for a licensed GSP/IRP. Implement credentials, transport and error mapping here."""
    def generate(self, invoice):
        raise NotImplementedError('Configure a licensed GSP/IRP adapter before enabling live e-invoicing.')
    def cancel(self, invoice):
        raise NotImplementedError('Configure a licensed GSP/IRP adapter before enabling live e-invoicing.')
