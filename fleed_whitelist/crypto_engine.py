import os
import hmac
import hashlib
import base64
import json
import time
import secrets
from typing import Dict, Tuple, Optional, List
import pyotp
import qrcode
import io

MASTER_SECRET = os.getenv("FLEED_MASTER_SECRET", "fleed_guard_super_secret_master_key_2026_x89a!")

class CryptoEngine:
    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """Hashes password with PBKDF2-HMAC-SHA256 and salt."""
        if not salt:
            salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            200_000
        )
        return key.hex(), salt

    @staticmethod
    def verify_password(password: str, password_hash: str, salt: str) -> bool:
        """Verifies candidate password against stored hash."""
        computed_hash, _ = CryptoEngine.hash_password(password, salt)
        return hmac.compare_digest(computed_hash, password_hash)

    # ---------------- 2FA (TOTP) Methods ----------------
    @staticmethod
    def generate_totp_secret() -> str:
        """Generates a base32 TOTP secret."""
        return pyotp.random_base32()

    @staticmethod
    def get_totp_uri(secret: str, username: str, issuer: str = "FleedGuard") -> str:
        """Generates otpauth URI for QR codes."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=username, issuer_name=issuer)

    @staticmethod
    def generate_qr_data_uri(totp_uri: str) -> str:
        """Generates a Base64 PNG data URI for the TOTP QR Code."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(totp_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#FACC15", back_color="#0A0A0C")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"

    @staticmethod
    def verify_totp(secret: str, code: str) -> bool:
        """Verifies 6-digit TOTP code (accepts 1 time-step drift)."""
        if not secret or not code:
            return False
        totp = pyotp.TOTP(secret)
        return totp.verify(code.strip().replace(" ", ""), valid_window=1)

    @staticmethod
    def generate_backup_codes(count: int = 8) -> List[str]:
        """Generates single-use 8-character hex recovery codes."""
        return [secrets.token_hex(4).upper() for _ in range(count)]

    # ---------------- Auth Tokens (Sessions) ----------------
    @staticmethod
    def create_session_token(user_id: int, username: str, role: str, expires_in_sec: int = 86400 * 7) -> str:
        """Creates a signed, tamper-proof session JWT-like token."""
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": user_id,
            "usr": username,
            "role": role,
            "iat": int(time.time()),
            "exp": int(time.time()) + expires_in_sec,
            "nonce": secrets.token_hex(8)
        }
        b64_header = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        b64_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        unsigned = f"{b64_header}.{b64_payload}"
        signature = hmac.new(MASTER_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest()
        b64_sig = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        return f"{unsigned}.{b64_sig}"

    @staticmethod
    def verify_session_token(token: str) -> Optional[Dict]:
        """Verifies session token integrity and expiration."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            b64_header, b64_payload, b64_sig = parts
            unsigned = f"{b64_header}.{b64_payload}"
            expected_sig = hmac.new(MASTER_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest()
            actual_sig = base64.urlsafe_b64decode(b64_sig + "==")
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None
            
            payload_json = base64.urlsafe_b64decode(b64_payload + "==").decode()
            payload = json.loads(payload_json)
            if payload.get("exp", 0) < time.time():
                return None
            return payload
        except Exception:
            return None

    # ---------------- Anti-Tamper & Handshake Cryptography ----------------
    @staticmethod
    def normalize_hwid(hwid: str) -> str:
        """Standardizes and hashes HWID to avoid executor-specific formatting leaks."""
        clean = hwid.strip().lower().replace("-", "").replace("{", "").replace("}", "")
        return hashlib.sha256(clean.encode()).hexdigest()

    @staticmethod
    def create_handshake_challenge(script_id: int, license_key: str, client_challenge: str) -> Dict:
        """Creates an ephemeral session challenge to defeat replay and MITM attacks."""
        nonce = secrets.token_hex(16)
        server_challenge = secrets.token_hex(16)
        expires_at = int(time.time()) + 30 # 30-second handshake window
        
        # Derive unique session encryption key
        session_seed = f"{nonce}:{server_challenge}:{client_challenge}:{MASTER_SECRET}"
        session_key = hashlib.sha256(session_seed.encode()).hexdigest()

        return {
            "nonce": nonce,
            "server_challenge": server_challenge,
            "session_key": session_key,
            "expires_at": expires_at
        }

    @staticmethod
    def verify_client_signature(
        client_signature: str,
        client_challenge: str,
        server_challenge: str,
        nonce: str,
        license_key: str,
        hwid: str,
        raw_hwid: Optional[str] = None
    ) -> bool:
        """Verifies that the executor client mathematically signed the challenge with HWID & Key."""
        client_sig_clean = client_signature.strip().lower()

        # Candidates for HWID field in signature
        candidates = [hwid]
        if raw_hwid:
            candidates.append(raw_hwid)
            candidates.append(CryptoEngine.normalize_hwid(raw_hwid))

        for cand in candidates:
            if not cand:
                continue
            # SHA256 Candidate
            expected_raw = f"{client_challenge}:{server_challenge}:{nonce}:{license_key}:{cand}"
            expected_sig = hashlib.sha256(expected_raw.encode('utf-8')).hexdigest().lower()
            if hmac.compare_digest(expected_sig, client_sig_clean):
                return True

            # FNV-1a 32-bit fallback for lightweight executors
            h = 0x811c9dc5
            for b in expected_raw.encode('utf-8'):
                h = (h ^ b) & 0xFFFFFFFF
                h = (h * 0x01000193) & 0xFFFFFFFF
            fnv_sig = f"{h:08x}".lower()
            if hmac.compare_digest(fnv_sig, client_sig_clean):
                return True

        return False

    @staticmethod
    def encrypt_payload(source_code: str, session_key: str, nonce: str) -> Tuple[str, str]:
        """
        Encrypts the script payload with dynamic multi-round RC4/ChaCha-style stream cipher
        with dynamic key rotation so it can be unpacked directly in-memory inside the client Luau VM.
        """
        key_bytes = (session_key + nonce).encode('utf-8')
        data_bytes = source_code.encode('utf-8')
        
        # Stream encryption suitable for zero-dependency execution inside Roblox Lua VM
        # RC4-like KSA/PRGA dynamic stream cipher with dynamic S-box permutation
        S = list(range(256))
        j = 0
        for i in range(256):
            j = (j + S[i] + key_bytes[i % len(key_bytes)]) % 256
            S[i], S[j] = S[j], S[i]

        i = j = 0
        cipher = bytearray()
        for byte in data_bytes:
            i = (i + 1) % 256
            j = (j + S[i]) % 256
            S[i], S[j] = S[j], S[i]
            k = S[(S[i] + S[j]) % 256]
            cipher.append(byte ^ k)

        encrypted_b64 = base64.b64encode(cipher).decode()
        auth_tag = hmac.new(key_bytes, cipher, hashlib.sha256).hexdigest()
        return encrypted_b64, auth_tag

crypto_engine = CryptoEngine()
