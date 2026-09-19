from app.gst import calculate_line, calculate_invoice, Scheme

def test_intrastate():
    x=calculate_line(2,1000,18,Scheme.REGULAR,'33','33')
    assert x['cgst']==180 and x['sgst']==180 and x['igst']==0 and x['total']==2360

def test_interstate():
    x=calculate_line(2,1000,18,Scheme.REGULAR,'33','29')
    assert x['cgst']==0 and x['sgst']==0 and x['igst']==360 and x['total']==2360

def test_composition_no_customer_tax():
    x=calculate_line(2,1000,1,Scheme.COMPOSITION,'33','33')
    assert x['cgst']==0 and x['sgst']==0 and x['igst']==0 and x['total']==2000
