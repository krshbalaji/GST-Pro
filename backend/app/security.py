import hashlib, hmac, os, secrets
from datetime import datetime, timezone, timedelta
import threading
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
REFRESH_TOKEN_DAYS=int(os.getenv("REFRESH_TOKEN_DAYS","7"))
REFRESH_TOKEN_BYTES=48

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
    payload={
        "sub":str(user["id"]),
        "company_id":str(user["company_id"]),
        "role":user["role"],
        "iat":int(now.timestamp()),
        "exp":int((now+timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
        "jti":secrets.token_hex(16),
    }
    return jwt.encode(payload,_secret(),algorithm=JWT_ALGORITHM)

def decode_token(token):
    return jwt.decode(token,_secret(),algorithms=[JWT_ALGORITHM])


def create_refresh_token():
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthRateLimiter:
    """Small in-process limiter for authentication endpoints.

    This is intentionally scoped to auth abuse protection. A multi-instance
    deployment should enforce a shared limiter at the API gateway/WAF layer.
    """
    def __init__(self, limit=5, window_seconds=60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events = {}
        self._lock = threading.Lock()

    def allow(self, key, now=None):
        now = now if now is not None else datetime.now(timezone.utc).timestamp()
        with self._lock:
            cutoff = now - self.window_seconds
            events = [ts for ts in self._events.get(key, []) if ts > cutoff]
            if len(events) >= self.limit:
                self._events[key] = events
                return False
            events.append(now)
            self._events[key] = events
            return True

    def reset(self):
        with self._lock:
            self._events.clear()

AUTH_RATE_LIMITER = AuthRateLimiter(
    limit=int(os.getenv("AUTH_RATE_LIMIT", "5")),
    window_seconds=int(os.getenv("AUTH_RATE_WINDOW_SECONDS", "60")),
)
