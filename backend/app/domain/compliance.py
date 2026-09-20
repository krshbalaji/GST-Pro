from dataclasses import dataclass

@dataclass(frozen=True)
class ReturnPeriod:
    gstin_id: str
    return_type: str
    period: str
    status: str

class ComplianceRules:
    @staticmethod
    def period(invoice_date: str) -> str:
        return invoice_date[:7]

    @staticmethod
    def assert_open(rows, gstin_id: str, invoice_date: str) -> None:
        period = ComplianceRules.period(invoice_date)
        for row in rows:
            if row.gstin_id == gstin_id and row.period == period and row.status == 'LOCKED':
                raise ValueError(f'Return period {period} is locked')
