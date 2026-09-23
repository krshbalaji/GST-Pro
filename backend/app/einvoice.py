from abc import ABC, abstractmethod
import hashlib, uuid
from .gst import financial_year

class EInvoiceProviderNotConfigured(RuntimeError):
    """Raised when live IRP filing is selected without a configured licensed adapter."""


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
    """Explicit live-IRP boundary; a licensed GSP/IRP adapter must be configured before use."""
    def generate(self, invoice):
        raise EInvoiceProviderNotConfigured(
            'Live e-invoice filing is not configured. Set up a licensed GSP/IRP adapter, credentials, transport and response mapping before setting MOCK_EINVOICE=false.'
        )
    def cancel(self, invoice):
        raise EInvoiceProviderNotConfigured(
            'Live e-invoice cancellation is not configured. Set up a licensed GSP/IRP adapter, credentials, transport and response mapping before setting MOCK_EINVOICE=false.'
        )
