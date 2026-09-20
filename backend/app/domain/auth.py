from dataclasses import dataclass

@dataclass(frozen=True)
class UserContext:
    user_id: str
    company_id: str
    role: str

class TenantAuthorization:
    def require_company(self, context: UserContext, company_id: str):
        if context.company_id != company_id:
            raise PermissionError('Cross-company access denied')
