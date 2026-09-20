from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException


def _audit_event(action, entity_type, entity_id, new=None, old=None, company_id=None, user_id=None, previous_hash="GENESIS"):
    payload = {
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "old_value": copy.deepcopy(old),
        "new_value": copy.deepcopy(new),
        "company_id": company_id,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "previous_hash": previous_hash,
    }
    payload["hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return {"id": str(uuid.uuid4()), **payload}


class ProductionInvoiceLifecycle:
    """Transaction-oriented production invoice orchestration."""

    def __init__(self, repositories, transaction_factory):
        self.repos = repositories
        self.transaction_factory = transaction_factory

    def _previous_hash(self, company_id, conn):
        row = self.repos["audit"]._one(
            "SELECT event_hash FROM audit_logs WHERE company_id=%s ORDER BY created_at DESC, id DESC LIMIT 1",
            (self.repos["invoices"]._invoice_company_id(self.repos["invoices"]._load(
                self.repos["invoices"]._load if False else None) if False else None),),
            conn,
        ) if False else None
        rows = self.repos["audit"]._all(
            "SELECT event_hash FROM audit_logs WHERE company_id=%s ORDER BY created_at DESC, id DESC LIMIT 1",
            (self.repos["invoices"]._uuid(company_id) if hasattr(self.repos["invoices"], "_uuid") else company_id,),
            conn,
        )
        return (rows[0]["event_hash"] if rows and rows[0]["event_hash"] else "GENESIS")

    def create(self, row, company_id, user_id=None):
        with self.transaction_factory() as conn:
            created = self.repos["invoices"].create(row, conn=conn)
            event = _audit_event("CREATE","INVOICE",created["id"],created,company_id=company_id,user_id=user_id)
            self.repos["audit"].append(event, conn=conn)
            return created

    def submit(self, invoice_id, company_id, user_id):
        with self.transaction_factory() as conn:
            current = self.repos["invoices"].get_for_update(invoice_id, conn)
            if not current:
                raise HTTPException(404, "Invoice not found")
            if current["request"].get("company_id") != company_id:
                raise HTTPException(403, "Cross-company access denied")
            if current["status"] not in ("DRAFT","REJECTED"):
                raise HTTPException(409, "Only draft or rejected invoices can be submitted for approval.")
            from .repositories.postgres import validate_invoice_transition
            validate_invoice_transition(current["status"], "PENDING_APPROVAL")
            updated = self.repos["invoices"].save({**current,"status":"PENDING_APPROVAL"}, conn=conn, expected_status=current["status"])
            approval = {
                "id": str(uuid.uuid4()), "invoice_id": invoice_id, "status":"PENDING",
                "submitted_by": user_id, "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
            approval = self.repos["approvals"].save(approval, conn=conn)
            event = _audit_event("SUBMIT_APPROVAL","INVOICE",invoice_id,approval,old=current,company_id=company_id,user_id=user_id)
            self.repos["audit"].append(event, conn=conn)
            return approval

    def decide(self, invoice_id, company_id, user_id, decision, comment=""):
        if decision not in ("APPROVE","REJECT"):
            raise HTTPException(422, "Decision must be APPROVE or REJECT")
        with self.transaction_factory() as conn:
            current = self.repos["invoices"].get_for_update(invoice_id, conn)
            if not current:
                raise HTTPException(404, "Invoice not found")
            if current["request"].get("company_id") != company_id:
                raise HTTPException(403, "Cross-company access denied")
            approval = self.repos["approvals"].get(invoice_id)
            if not approval or approval.get("status") != "PENDING":
                raise HTTPException(409, "Invoice approval is not pending")
            if str(approval.get("submitted_by")) == str(user_id):
                raise HTTPException(409, "Maker-checker control: the submitting user cannot approve the same invoice.")
            target = "APPROVED" if decision == "APPROVE" else "REJECTED"
            from .repositories.postgres import validate_invoice_transition
            validate_invoice_transition(current["status"], target)
            updated = self.repos["invoices"].save({**current,"status":target}, conn=conn, expected_status=current["status"])
            approval = {**approval,"status":decision,"comment":comment,"approved_by":user_id,"approved_at":datetime.now(timezone.utc).isoformat()}
            approval = self.repos["approvals"].save(approval, conn=conn)
            event = _audit_event(decision,"INVOICE",invoice_id,approval,old=current,company_id=company_id,user_id=user_id)
            self.repos["audit"].append(event, conn=conn)
            return approval

    def cancel(self, invoice_id, company_id, user_id, action="CANCEL"):
        with self.transaction_factory() as conn:
            current = self.repos["invoices"].get_for_update(invoice_id, conn)
            if not current: raise HTTPException(404,"Invoice not found")
            if current["request"].get("company_id") != company_id:
                raise HTTPException(403,"Cross-company access denied")
            from .repositories.postgres import validate_invoice_transition
            validate_invoice_transition(current["status"],"CANCELLED")
            updated = self.repos["invoices"].save({**current,"status":"CANCELLED"}, conn=conn, expected_status=current["status"])
            event = _audit_event(action,"INVOICE",invoice_id,{"status":"CANCELLED"},old=current,company_id=company_id,user_id=user_id)
            self.repos["audit"].append(event, conn=conn)
            return updated
