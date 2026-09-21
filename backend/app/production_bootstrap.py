from __future__ import annotations

from uuid import UUID, uuid4

from .security import hash_password

BOOTSTRAP_COMPANY_ID = UUID("00000000-0000-0000-0000-000000000001")
BOOTSTRAP_GSTIN_ID = UUID("00000000-0000-0000-0000-000000000002")
BOOTSTRAP_OWNER_ID = UUID("00000000-0000-0000-0000-000000000003")
BOOTSTRAP_CA_ID = UUID("00000000-0000-0000-0000-000000000004")
BOOTSTRAP_CUSTOMER_1 = UUID("00000000-0000-0000-0000-000000000011")
BOOTSTRAP_CUSTOMER_2 = UUID("00000000-0000-0000-0000-000000000012")
BOOTSTRAP_PRODUCT_1 = UUID("00000000-0000-0000-0000-000000000021")
BOOTSTRAP_PRODUCT_2 = UUID("00000000-0000-0000-0000-000000000022")
BOOTSTRAP_PRODUCT_3 = UUID("00000000-0000-0000-0000-000000000023")


def bootstrap_production(store) -> None:
    """Create the minimal local development tenant once, when explicitly enabled."""
    if str(__import__("os").getenv("GSTPRO_BOOTSTRAP", "0")).lower() not in {"1", "true", "yes"}:
        return

    with store.connect() as conn:
        company_exists = conn.execute("SELECT id FROM companies WHERE id=%s", (BOOTSTRAP_COMPANY_ID,)).fetchone()
        if not company_exists:
            conn.execute(
                """INSERT INTO companies (id,legal_name,trade_name,pan,aato,address)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
                (BOOTSTRAP_COMPANY_ID,"SARO DEVI ENTERPRISES","Saro Devi Enterprises","ABCDE1234F",45000000,
                 '{"line1":"123, North Veli Street","city":"Madurai","state":"Tamil Nadu","pincode":"625001"}'),
            )

        conn.execute(
            """INSERT INTO gstins (id,company_id,gstin,state_code,scheme,legal_name,trade_name,is_active)
               VALUES (%s,%s,%s,%s,%s,%s,%s,true)
               ON CONFLICT (id) DO NOTHING""",
            (BOOTSTRAP_GSTIN_ID,BOOTSTRAP_COMPANY_ID,"33ABCDE1234F1Z5","33","REGULAR","SARO DEVI ENTERPRISES","Saro Devi Enterprises"),
        )

        owner_hash = hash_password("admin")
        ca_hash = hash_password("caadmin123")
        conn.execute(
            """INSERT INTO users (id,company_id,name,email,role,password_hash,is_active)
               VALUES (%s,%s,%s,%s,%s,%s,true)
               ON CONFLICT (email) DO NOTHING""",
            (BOOTSTRAP_OWNER_ID,BOOTSTRAP_COMPANY_ID,"Admin","admin@gstpro.local","OWNER",owner_hash),
        )
        conn.execute(
            """INSERT INTO users (id,company_id,name,email,role,password_hash,is_active)
               VALUES (%s,%s,%s,%s,%s,%s,true)
               ON CONFLICT (email) DO NOTHING""",
            (BOOTSTRAP_CA_ID,BOOTSTRAP_COMPANY_ID,"Demo CA","ca@gstpro.local","CA",ca_hash),
        )

        customers = [
            (BOOTSTRAP_CUSTOMER_1,"ABC Traders","33AACFA1234A1Z1","33",'{"line1":"123, Anna Salai","city":"Chennai","state":"Tamil Nadu","pincode":"600002"}'),
            (BOOTSTRAP_CUSTOMER_2,"Bharat Karnataka Stores","29AACFA1234A1Z1","29",'{"line1":"MG Road","city":"Bengaluru","state":"Karnataka","pincode":"560001"}'),
        ]
        for cid,name,gstin,state,address in customers:
            conn.execute(
                """INSERT INTO customers (id,company_id,name,gstin,state_code,address,is_active)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,true)
                   ON CONFLICT (id) DO NOTHING""",
                (cid,BOOTSTRAP_COMPANY_ID,name,gstin,state,address),
            )

        products = [
            (BOOTSTRAP_PRODUCT_1,"Cotton Shirt (Men)","620520","PCS",500,18),
            (BOOTSTRAP_PRODUCT_2,"Towel (Home Textile)","630260","PCS",300,12),
            (BOOTSTRAP_PRODUCT_3,"IT Consulting","998313","HRS",2500,18),
        ]
        for pid,description,hsn,unit,rate,gst_rate in products:
            conn.execute(
                """INSERT INTO products (id,company_id,description,hsn_sac,unit,rate,gst_rate,taxable,is_service,active)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,true,%s,true)
                   ON CONFLICT (id) DO NOTHING""",
                (pid,BOOTSTRAP_COMPANY_ID,description,hsn,unit,rate,gst_rate,description=="IT Consulting"),
            )

        mappings = [
            ("company","demo-company",BOOTSTRAP_COMPANY_ID),
            ("gstin","demo-gstin",BOOTSTRAP_GSTIN_ID),
            ("user","U1",BOOTSTRAP_OWNER_ID),
            ("user","U2",BOOTSTRAP_CA_ID),
            ("customer","C1",BOOTSTRAP_CUSTOMER_1),
            ("customer","C2",BOOTSTRAP_CUSTOMER_2),
            ("product","P1",BOOTSTRAP_PRODUCT_1),
            ("product","P2",BOOTSTRAP_PRODUCT_2),
            ("product","P3",BOOTSTRAP_PRODUCT_3),
        ]
        for entity_type,domain_id,database_id in mappings:
            conn.execute(
                """INSERT INTO gstpro_id_map (entity_type,domain_id,database_id)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (entity_type,domain_id) DO NOTHING""",
                (entity_type,domain_id,database_id),
            )

        conn.commit()
