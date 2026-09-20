from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Party:
    company_id: str
    name: str
    gstin: Optional[str] = None
    state_code: Optional[str] = None
    pan: Optional[str] = None
