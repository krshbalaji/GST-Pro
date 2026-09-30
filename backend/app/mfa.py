import base64, hashlib, json, os, secrets
from datetime import datetime, timezone, timedelta
import pyotp
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MFA_CHALLENGE_MINUTES = int(os.getenv("MFA_CHALLENGE_MINUTES", "5"))

def _key():
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32:
        secret = "dev-only-gst-pro-secret-change-me-0123456789"
    return hashlib.sha256(("GSTPRO-MFA|" + secret).encode()).digest()

def encrypt_secret(secret: str) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, secret.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()

def decrypt_secret(encoded: str) -> str:
    raw = base64.urlsafe_b64decode(encoded.encode())
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode()

def new_secret() -> str:
    return pyotp.random_base32(32)

def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="GST Pro")

def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)

def generate_recovery_codes(count: int = 8) -> list[str]:
    return [secrets.token_hex(5).upper() for _ in range(count)]

def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()

def hash_recovery_codes(codes: list[str]) -> list[str]:
    return [hash_recovery_code(code) for code in codes]

def consume_recovery_code(stored_hashes: list[str], code: str) -> tuple[bool, list[str]]:
    candidate = hash_recovery_code(code)
    if candidate not in stored_hashes:
        return False, stored_hashes
    remaining = list(stored_hashes)
    remaining.remove(candidate)
    return True, remaining

def challenge_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=MFA_CHALLENGE_MINUTES)


def make_challenge(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "purpose": "mfa_challenge",
        "iat": int(now.timestamp()),
        "exp": int(challenge_expiry().timestamp()),
        "jti": secrets.token_hex(16),
    }
    secret = os.getenv("JWT_SECRET", "") or "dev-only-gst-pro-secret-change-me-0123456789"
    token = jwt.encode(payload, secret, algorithm=os.getenv("JWT_ALGORITHM", "HS256"))
    register_challenge(payload["jti"], payload["sub"], datetime.fromtimestamp(payload["exp"], timezone.utc))
    return token

def decode_challenge(token: str) -> dict:
    secret = os.getenv("JWT_SECRET", "") or "dev-only-gst-pro-secret-change-me-0123456789"
    payload = jwt.decode(token, secret, algorithms=[os.getenv("JWT_ALGORITHM", "HS256")])
    if payload.get("purpose") != "mfa_challenge":
        raise ValueError("Invalid MFA challenge")
    return payload



_MFA_CHALLENGES = {}

def _challenge_store():
    return _MFA_CHALLENGES

def register_challenge(jti: str, user_id: str, expires_at: datetime) -> None:
    if os.getenv("GSTPRO_MODE", "demo").lower() in {"production", "prod"}:
        from .storage import transaction
        with transaction() as conn:
            conn.execute("DELETE FROM mfa_challenges WHERE expires_at <= now()")
            conn.execute("INSERT INTO mfa_challenges (jti,user_id,expires_at) VALUES (%s,%s,%s)", (jti, user_id, expires_at))
    else:
        _challenge_store()[jti] = {"user_id": str(user_id), "expires_at": expires_at, "consumed": False}

def consume_challenge(jti: str, user_id: str) -> bool:
    if os.getenv("GSTPRO_MODE", "demo").lower() in {"production", "prod"}:
        from .storage import transaction
        with transaction() as conn:
            row = conn.execute(
                """UPDATE mfa_challenges
                   SET consumed_at = now()
                   WHERE jti=%s AND user_id=%s AND consumed_at IS NULL AND expires_at > now()
                   RETURNING jti""",
                (jti, user_id),
            ).fetchone()
            return row is not None
    row = _challenge_store().get(jti)
    if not row or row["user_id"] != str(user_id) or row["consumed"] or row["expires_at"] <= datetime.now(timezone.utc):
        return False
    row["consumed"] = True
    return True
