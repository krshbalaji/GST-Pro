from dataclasses import dataclass
from decimal import Decimal
from ..gst import Scheme, calculate_invoice

@dataclass(frozen=True)
class InvoiceTotals:
    taxable_value: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal

class InvoiceRules:
    @staticmethod
    def calculate(lines, scheme: Scheme, supplier_state: str, place_of_supply: str):
        return calculate_invoice(lines, scheme, supplier_state, place_of_supply)

    @staticmethod
    def is_composition_taxed_invoice(invoice_type: str, scheme: Scheme) -> bool:
        return invoice_type == 'TAX_INVOICE' and scheme == Scheme.COMPOSITION
