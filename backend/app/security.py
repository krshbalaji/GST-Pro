import hashlib, hmac, os, secrets
from datetime import datetime, timezone, timedelta
import jwt

ROLES={
    "OWNER":{"read","create","edit","approve","lock","admin"},
    "ACCOUNTANT":{"read","create","edit"},
    "CA":{"read","approve","lock"},
    "VIEWER":{"read"},
}
JWT_SECRET=os.getenv("JWT_SECRET","")
JWT_ALGORITHM=os.getenv("JWT_ALGORITHM","HS256")
ACCESS_TOKEN_MINUTES=int(os.getenv("ACCESS_TOKEN_MINUTES","30"))

def require_runtime_security():
    if os.getenv("ENVIRONMENT","development").lower() in {"production","prod"} and len(JWT_SECRET)<32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters in production.")

def _secret():
    return JWT_SECRET or "dev-only-gst-pro-secret-change-me-0123456789"

def hash_password(password:str)->str:
    salt=os.urandom(16)
    dk=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,210000)
    return "pbkdf2_sha256$210000$"+salt.hex()+"$"+dk.hex()

def verify_password(password:str,encoded:str)->bool:
    try:
        _,rounds,salt_hex,digest=encoded.split("$")
        got=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt_hex),int(rounds)).hex()
        return hmac.compare_digest(got,digest)
    except Exception:
        return False

def make_token(user):
    now=datetime.now(timezone.utc)
    payload={"sub":user["id"],"company_id":user["company_id"],"role":user["role"],
             "iat":int(now.timestamp()),"exp":int((now+timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
             "jti":secrets.token_hex(16)}
    return jwt.encode(payload,_secret(),algorithm=JWT_ALGORITHM)

def decode_token(token):
    return jwt.decode(token,_secret(),algorithms=[JWT_ALGORITHM])
