import pytest

from app.einvoice import GSPIRPProvider, EInvoiceProviderNotConfigured


def test_live_irp_provider_fails_closed_until_configured():
    provider = GSPIRPProvider()
    with pytest.raises(EInvoiceProviderNotConfigured, match='MOCK_EINVOICE=false'):
        provider.generate({'request': {}})
    with pytest.raises(EInvoiceProviderNotConfigured, match='MOCK_EINVOICE=false'):
        provider.cancel({'request': {}})
