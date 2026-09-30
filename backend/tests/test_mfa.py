import os
os.environ.setdefault("GSTPRO_MODE", "demo")

from fastapi.testclient import TestClient
import pyotp

from app.main import app, USERS
from app.security import AUTH_RATE_LIMITER

client = TestClient(app)

def test_totp_mfa_enroll_confirm_login_and_recovery_code():
    AUTH_RATE_LIMITER.reset()
    user = USERS["U1"]
    user.pop("mfa_enabled", None)
    user.pop("mfa_secret_encrypted", None)
    user.pop("mfa_pending_secret_encrypted", None)
    user.pop("mfa_recovery_codes", None)
    user.pop("mfa_confirmed_at", None)
    user.pop("mfa_last_totp_counter", None)

    login = client.post("/api/auth/login", json={"email":"admin@gstpro.local","password":"admin"})
    assert login.status_code == 200
    access = login.json()["access_token"]

    enrolled = client.post("/api/auth/mfa/enroll", headers={"Authorization":f"Bearer {access}"})
    assert enrolled.status_code == 200
    body = enrolled.json()
    assert body["status"] == "pending"
    assert body["secret"]
    assert body["provisioning_uri"].startswith("otpauth://totp/")
    assert len(body["recovery_codes"]) == 8

    secret = body["secret"]
    code = pyotp.TOTP(secret).now()
    confirmed = client.post("/api/auth/mfa/confirm", headers={"Authorization":f"Bearer {access}"}, json={"code":code})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "enabled"

    blocked = client.post("/api/auth/login", json={"email":"admin@gstpro.local","password":"admin"})
    assert blocked.status_code == 200
    challenge = blocked.json()
    assert challenge["mfa_required"] is True
    assert "access_token" not in challenge

    second_code = pyotp.TOTP(secret).now()
    verified = client.post("/api/auth/mfa/verify", json={"challenge_token":challenge["challenge_token"],"code":second_code})
    assert verified.status_code == 200
    assert verified.json()["access_token"]

    recovery_login = client.post("/api/auth/login", json={"email":"admin@gstpro.local","password":"admin"})
    recovery = client.post("/api/auth/mfa/verify", json={"challenge_token":recovery_login.json()["challenge_token"],"code":body["recovery_codes"][0]})
    assert recovery.status_code == 200
    assert recovery.json()["access_token"]

    reused = client.post("/api/auth/mfa/verify", json={"challenge_token":recovery_login.json()["challenge_token"],"code":body["recovery_codes"][0]})
    assert reused.status_code == 401

    single_use_login = client.post("/api/auth/login", json={"email":"admin@gstpro.local","password":"admin"})
    single_use_challenge = single_use_login.json()["challenge_token"]
    first_use = client.post("/api/auth/mfa/verify", json={"challenge_token":single_use_challenge,"code":body["recovery_codes"][1]})
    assert first_use.status_code == 200
    replay = client.post("/api/auth/mfa/verify", json={"challenge_token":single_use_challenge,"code":body["recovery_codes"][2]})
    assert replay.status_code == 401

    disabled = client.post("/api/auth/mfa/disable", headers={"Authorization":f"Bearer {access}"}, json={"password":"admin","code":pyotp.TOTP(secret).now()})
    assert disabled.status_code == 200
    assert user.get("mfa_confirmed_at") is None
    assert user.get("mfa_last_totp_counter") is None
    plain_login = client.post("/api/auth/login", json={"email":"admin@gstpro.local","password":"admin"})
    assert plain_login.status_code == 200
    assert "access_token" in plain_login.json()
    AUTH_RATE_LIMITER.reset()
