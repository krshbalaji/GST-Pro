from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

P = Decimal

class Scheme(str, Enum):
    REGULAR = 'REGULAR'
    COMPOSITION = 'COMPOSITION'

def money(v):
    return P(str(v)).quantize(P('0.01'), rounding=ROUND_HALF_UP)

def hsn_min_digits(aato: Decimal | float | int) -> int:
    return 6 if P(str(aato)) > P('50000000') else 4

def financial_year(date_str: str) -> str:
    y, m, _ = map(int, date_str[:10].split('-'))
    return f'{y-1}-{str(y)[-2:]}' if m < 4 else f'{y}-{str(y+1)[-2:]}'

def calculate_line(qty, rate, gst_rate, scheme, supplier_state, place_of_supply):
    qty, rate, gst_rate = P(str(qty)), P(str(rate)), P(str(gst_rate))
    taxable = money(qty * rate)
    if scheme == Scheme.COMPOSITION:
        return {'taxable_value': taxable, 'cgst': P('0'), 'sgst': P('0'), 'igst': P('0'), 'total': taxable, 'supply_type': 'COMPOSITION'}
    if supplier_state == place_of_supply:
        half = gst_rate / 2
        cgst = money(taxable * half / 100)
        sgst = money(taxable * half / 100)
        return {'taxable_value': taxable, 'cgst': cgst, 'sgst': sgst, 'igst': P('0'), 'total': taxable + cgst + sgst, 'supply_type': 'INTRA_STATE'}
    igst = money(taxable * gst_rate / 100)
    return {'taxable_value': taxable, 'cgst': P('0'), 'sgst': P('0'), 'igst': igst, 'total': taxable + igst, 'supply_type': 'INTER_STATE'}

def calculate_invoice(lines, scheme, supplier_state, place_of_supply):
    out = {'taxable_value': P('0'), 'cgst': P('0'), 'sgst': P('0'), 'igst': P('0'), 'total': P('0'), 'supply_type': 'COMPOSITION' if scheme == Scheme.COMPOSITION else ('INTRA_STATE' if supplier_state == place_of_supply else 'INTER_STATE')}
    calculated=[]
    for line in lines:
        c=calculate_line(line['qty'],line['rate'],line['gst_rate'],scheme,supplier_state,place_of_supply)
        calculated.append({**line,**c})
        for k in ('taxable_value','cgst','sgst','igst','total'): out[k]+=c[k]
    for k in ('taxable_value','cgst','sgst','igst','total'): out[k]=money(out[k])
    return {**out,'lines':calculated}
