import hashlib, hmac, os
from datetime import datetime, timezone
import jwt

ROLES={
 'OWNER': {'read','create','edit','approve','lock','admin'},
 'ACCOUNTANT': {'read','create','edit'},
 'CA': {'read','approve','lock'},
 'VIEWER': {'read'},
}

def hash_password(password:str)->str:
    salt=os.urandom(16)
    dk=hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 210000)
    return 'pbkdf2_sha256$210000$'+salt.hex()+'$'+dk.hex()

def verify_password(password:str, encoded:str)->bool:
    try:
        _, rounds, salt_hex, digest=encoded.split('$')
        got=hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), int(rounds)).hex()
        return hmac.compare_digest(got,digest)
    except Exception:
        return False

def make_token(user):
    now=int(datetime.now(timezone.utc).timestamp())
    return jwt.encode({'sub':user['id'],'company_id':user['company_id'],'role':user['role'],'iat':now,'exp':now+8*3600}, os.getenv('JWT_SECRET','gst-pro-production-secret-change-me-please-set-env'), algorithm='HS256')

def decode_token(token):
    return jwt.decode(token, os.getenv('JWT_SECRET','gst-pro-production-secret-change-me-please-set-env'), algorithms=['HS256'])
