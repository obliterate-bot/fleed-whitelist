import pytest
import os
import sys
import json
import time
import hashlib
import asyncio
import secrets
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fleed_whitelist.database import db
from fleed_whitelist.crypto_engine import crypto_engine
from fleed_whitelist.loader_generator import loader_generator
from fleed_whitelist.server import app

def test_crypto_engine_password_and_2fa():
    # 1. Password hashing & verification
    pw = "SuperSecurePassword123!"
    p_hash, salt = crypto_engine.hash_password(pw)
    assert crypto_engine.verify_password(pw, p_hash, salt) is True
    assert crypto_engine.verify_password("WrongPassword", p_hash, salt) is False

    # 2. TOTP 2FA secret & verification
    secret = crypto_engine.generate_totp_secret()
    assert len(secret) == 32
    uri = crypto_engine.get_totp_uri(secret, "testuser")
    assert "otpauth://" in uri
    
    qr_uri = crypto_engine.generate_qr_data_uri(uri)
    assert qr_uri.startswith("data:image/png;base64,")

    import pyotp
    totp = pyotp.TOTP(secret)
    current_token = totp.now()
    assert crypto_engine.verify_totp(secret, current_token) is True
    assert crypto_engine.verify_totp(secret, "000000") is False

    # 3. Backup recovery codes
    backup_codes = crypto_engine.generate_backup_codes(8)
    assert len(backup_codes) == 8
    assert all(len(c) == 8 for c in backup_codes)

def test_session_token():
    token = crypto_engine.create_session_token(user_id=42, username="testdev", role="developer")
    payload = crypto_engine.verify_session_token(token)
    assert payload is not None
    assert payload["sub"] == 42
    assert payload["usr"] == "testdev"

    tampered = token[:-4] + "abcd"
    assert crypto_engine.verify_session_token(tampered) is None

def test_in_memory_stream_decryption_match():
    """Verifies that in-memory RC4/stream decrypt recreates original script byte-for-byte."""
    original_script = "-- Fleed Elite Script\nlocal Player = game.Players.LocalPlayer\nprint('Score: ' .. 9999)\nreturn true"
    session_key = "d3adbeefcafe1234567890abcdef1234"
    nonce = "abcdef1234567890"

    encrypted_b64, auth_tag = crypto_engine.encrypt_payload(original_script, session_key, nonce)
    
    # Decrypt in Python replicating client Luau VM logic
    import base64
    cipher_bytes = list(base64.b64decode(encrypted_b64))
    key_bytes = (session_key + nonce).encode('utf-8')

    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key_bytes[i % len(key_bytes)]) % 256
        S[i], S[j] = S[j], S[i]

    i = j = 0
    decrypted = bytearray()
    for byte in cipher_bytes:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        k = S[(S[i] + S[j]) % 256]
        decrypted.append(byte ^ k)

    assert decrypted.decode('utf-8') == original_script

def test_full_handshake_and_tamper_defense():
    async def _run():
        await db.init()

        with TestClient(app) as client:
            # 1. Register a test user
            username = f"dev_{int(time.time())}"
            reg_resp = client.post("/api/auth/register", json={
                "username": username,
                "email": f"{username}@test.com",
                "password": "Password123!"
            })
            assert reg_resp.status_code == 200
            auth_token = reg_resp.json()["token"]
            headers = {"Authorization": f"Bearer {auth_token}"}

            # 2. Test 2FA Setup API flow
            setup_resp = client.post("/api/auth/2fa/setup", headers=headers)
            assert setup_resp.status_code == 200
            setup_data = setup_resp.json()
            assert "secret" in setup_data
            assert "qr_code" in setup_data
            assert len(setup_data["backup_codes"]) == 8

            # Activate 2FA with current valid TOTP code
            import pyotp
            totp = pyotp.TOTP(setup_data["secret"])
            code = totp.now()
            verify_2fa_resp = client.post("/api/auth/2fa/verify", json={"code": code}, headers=headers)
            assert verify_2fa_resp.status_code == 200
            assert verify_2fa_resp.json()["success"] is True

            # 3. Test 2FA Login Flow
            # Attempt login without 2FA code (must trigger requires_2fa)
            login_attempt1 = client.post("/api/auth/login", json={
                "username": username,
                "password": "Password123!"
            })
            assert login_attempt1.status_code == 200
            assert login_attempt1.json().get("requires_2fa") is True

            # Attempt login with backup recovery code
            backup_code_to_use = setup_data["backup_codes"][0]
            login_attempt2 = client.post("/api/auth/login", json={
                "username": username,
                "password": "Password123!",
                "two_factor_code": backup_code_to_use
            })
            assert login_attempt2.status_code == 200
            assert "token" in login_attempt2.json()

            # 4. Create an Unobfuscated script and a VM Protected script
            slug = f"hoopz_elite_{int(time.time())}"
            create_resp = client.post("/api/scripts", json={
                "name": "Hoopz Elite Aimbot",
                "slug": slug,
                "version": "1.2.0",
                "raw_source": "print('Hoopz Elite Aimbot Loaded Successfully!')\nlocal x = 100",
                "is_obfuscated_mode": 0 # Developer opted for Unobfuscated mode
            }, headers=headers)
            assert create_resp.status_code == 200
            script_id = create_resp.json()["id"]

            # 5. Generate a license key
            key_resp = client.post("/api/licenses/bulk", json={
                "script_id": script_id,
                "count": 1,
                "duration_days": 30,
                "note": "Test Customer Key"
            }, headers=headers)
            assert key_resp.status_code == 200
            license_key = key_resp.json()["keys"][0]

            # 6. Step 1: Handshake Initialization from Roblox Executor
            hwid = "TEST-HARDWARE-GUID-1234-5678"
            client_challenge = hashlib.sha256(b"random_client_challenge_seed").hexdigest()
            
            init_resp = client.post("/v1/handshake/init", json={
                "slug": slug,
                "key": license_key,
                "hwid": hwid,
                "client_challenge": client_challenge,
                "executor": "Synapse-Z"
            })
            assert init_resp.status_code == 200
            init_data = init_resp.json()
            assert init_data["success"] is True
            nonce = init_data["nonce"]
            server_challenge = init_data["server_challenge"]

            # 7. Step 2: Compute Client HMAC Proof Signature
            norm_hwid = crypto_engine.normalize_hwid(hwid)
            sig_payload = f"{client_challenge}:{server_challenge}:{nonce}:{license_key}:{norm_hwid}"
            client_sig = hashlib.sha256(sig_payload.encode()).hexdigest()

            # Verify Handshake
            verify_resp = client.post("/v1/handshake/verify", json={
                "nonce": nonce,
                "signature": client_sig,
                "client_challenge": client_challenge
            })
            assert verify_resp.status_code == 200
            verify_data = verify_resp.json()
            assert verify_data["success"] is True
            assert "payload" in verify_data
            assert "session_key" in verify_data
            assert verify_data["is_obfuscated"] is False # Properly reflects unobfuscated mode

            # 8. Test Tamper Attempt: Replaying with invalid signature must FAIL (403)
            init2 = client.post("/v1/handshake/init", json={
                "slug": slug,
                "key": license_key,
                "hwid": hwid,
                "client_challenge": client_challenge
            }).json()
            tampered_verify = client.post("/v1/handshake/verify", json={
                "nonce": init2["nonce"],
                "signature": "fake_forged_cracker_signature_00000",
                "client_challenge": client_challenge
            })
            assert tampered_verify.status_code == 403

            # 9. Test HWID Mismatch Defense: Request from different HWID must FAIL (403)
            mismatch_init = client.post("/v1/handshake/init", json={
                "slug": slug,
                "key": license_key,
                "hwid": "DIFFERENT_CRACKER_DEVICE_HWID",
                "client_challenge": client_challenge
            })
            assert mismatch_init.status_code == 403
            assert "HWID Mismatch" in mismatch_init.json()["message"]

            # 10. Test Killswitch Defense: Activating killswitch must instantly block all executions
            ks_resp = client.patch(f"/api/scripts/{script_id}", json={
                "killswitch_active": 1,
                "killswitch_reason": "Emergency script update in progress"
            }, headers=headers)
            assert ks_resp.status_code == 200

            blocked_init = client.post("/v1/handshake/init", json={
                "slug": slug,
                "key": license_key,
                "hwid": hwid,
                "client_challenge": client_challenge
            })
            assert blocked_init.status_code == 403
            assert "KILLSWITCH ACTIVE" in blocked_init.json()["message"]

            # 11. Test Frontend HTML and Loader endpoint
            loader_resp = client.get(f"/v1/loader/{slug}")
            assert loader_resp.status_code == 200
            assert "FleedGuard" in loader_resp.text

            getkey_resp = client.get(f"/getkey/{slug}")
            assert getkey_resp.status_code == 200
            assert "FleedGuard" in getkey_resp.text

    asyncio.run(_run())

def test_loader_generation():
    loader_code = loader_generator.generate_client_loader("https://fleed.bot", "my_script_slug", "My Hub")
    assert "FleedGuard" in loader_code
    assert "SCRIPT_SLUG = \"my_script_slug\"" in loader_code
    assert "/v1/handshake/init" in loader_code
    assert "/v1/handshake/verify" in loader_code
    assert "checkEnvironment()" in loader_code

def test_control_panel_view_and_redemption():
    async def _run():
        await db.init()

        # 1. Create a script in DB
        slug = f"panel_test_{int(time.time())}"
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        async with db.get_db() as conn:
            cursor = await conn.execute("""
                INSERT INTO scripts (user_id, name, slug, raw_source, created_at, updated_at)
                VALUES (1, 'Silver Surfer', ?, 'print(1)', ?, ?)
            """, (slug, now_iso, now_iso))
            await conn.commit()
            script_id = cursor.lastrowid

            # 2. Insert unlinked key
            key = f"FLEED-TEST-PANEL-{int(time.time())}-{secrets.token_hex(4)}"
            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, created_at)
                VALUES (?, ?, ?)
            """, (script_id, key, now_iso))
            await conn.commit()

            # 3. Simulate redemption by Discord User
            discord_user_id = "539594512981295106"
            await conn.execute("UPDATE licenses SET discord_id = ? WHERE license_key = ?", (discord_user_id, key))
            await conn.commit()

            # 4. Verify link
            cursor = await conn.execute("SELECT discord_id, hwid FROM licenses WHERE license_key = ?", (key,))
            row = await cursor.fetchone()
            assert row["discord_id"] == discord_user_id
            assert row["hwid"] is None

            # 5. Simulate HWID binding on run
            hwid_hash = hashlib.sha256(b"mock_device_hwid").hexdigest()
            await conn.execute("UPDATE licenses SET hwid = ? WHERE license_key = ?", (hwid_hash, key))
            await conn.commit()

            # 6. Simulate HWID Reset button click
            await conn.execute("UPDATE licenses SET hwid = NULL WHERE license_key = ?", (key,))
            await conn.commit()
            
            cursor = await conn.execute("SELECT hwid FROM licenses WHERE license_key = ?", (key,))
            assert (await cursor.fetchone())["hwid"] is None

            # 7. Simulate Unlink Key button click
            await conn.execute("UPDATE licenses SET discord_id = NULL WHERE license_key = ?", (key,))
            await conn.commit()

            cursor = await conn.execute("SELECT discord_id FROM licenses WHERE license_key = ?", (key,))
            assert (await cursor.fetchone())["discord_id"] is None

    asyncio.run(_run())

