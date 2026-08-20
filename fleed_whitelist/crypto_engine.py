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

# SECURITY: MASTER_SECRET must come from the environment. A hardcoded fallback
# would let anyone who reads the source forge session tokens, loader tokens, and
# handshake signatures. If it is missing we FAIL CLOSED: in production
# (FLEED_ENV=production) we refuse to start; otherwise we generate a random
# ephemeral secret for this process only (tokens reset on restart, which is safe).
_MASTER_SECRET_ENV = os.getenv("FLEED_MASTER_SECRET", "").strip()
if _MASTER_SECRET_ENV and len(_MASTER_SECRET_ENV) >= 32:
    MASTER_SECRET = _MASTER_SECRET_ENV
else:
    if os.getenv("FLEED_ENV", "").lower() == "production":
        raise RuntimeError(
            "FLEED_MASTER_SECRET is missing or too short (>=32 chars required). "
            "Refusing to start in production without a strong master secret."
        )
    import warnings as _warnings
    MASTER_SECRET = secrets.token_hex(32)
    _warnings.warn(
        "FLEED_MASTER_SECRET not set (or <32 chars). Using a RANDOM ephemeral "
        "secret for this process. Set FLEED_MASTER_SECRET in the environment for "
        "persistent, secure tokens.",
        RuntimeWarning,
    )

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
    def create_session_token(user_id: int, username: str, role: str, expires_in_sec: int = 86400 * 30) -> str:
        """Creates a signed, tamper-proof session JWT-like token (valid for 30 days)."""
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
            # SECURITY: pin the algorithm. Without this, an attacker could submit
            # a token with "alg":"none" (or a different alg) and bypass signature
            # checks on libraries that honor the header. We only accept HS256.
            try:
                header = json.loads(base64.urlsafe_b64decode(b64_header + "==").decode())
            except Exception:
                return None
            if not isinstance(header, dict) or header.get("alg") != "HS256":
                return None
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
    def derive_session_key(client_challenge: str, server_challenge: str, nonce: str, license_key: str, hwid: str) -> str:
        """
        Derives an ephemeral session key deterministically from the handshake parameters.
        Neither client nor server needs to transmit the encryption key across the network.
        """
        seed = f"{client_challenge}:{server_challenge}:{nonce}:{license_key}:{hwid}"
        return hashlib.sha256(seed.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_loader_token(script_slug: str, timestamp: Optional[int] = None) -> str:
        """Generates an HMAC loader integrity token bound to the script slug and short time window (90s)."""
        ts = timestamp or int(time.time())
        window = ts // 90 # 90-second rolling token window
        msg = f"loader_armor:{script_slug}:{window}"
        sig = hmac.new(MASTER_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:24]
        return f"{window}:{sig}"

    @staticmethod
    def verify_loader_token(token: str, script_slug: str) -> bool:
        """Verifies loader integrity token against current and previous time windows."""
        try:
            if not token or ":" not in token:
                return False
            window_str, sig = token.split(":", 1)
            token_window = int(window_str)
            current_window = int(time.time()) // 90
            
            # Allow current window and adjacent +/- 1 window (drift tolerance)
            if abs(current_window - token_window) > 1:
                return False
                
            expected_msg = f"loader_armor:{script_slug}:{token_window}"
            expected_sig = hmac.new(MASTER_SECRET.encode(), expected_msg.encode(), hashlib.sha256).hexdigest()[:24]
            return hmac.compare_digest(expected_sig, sig)
        except Exception:
            return False

    @staticmethod
    def create_handshake_challenge(script_id: int, license_key: str, client_challenge: str, hwid: str) -> Dict:
        """Creates an ephemeral session challenge to defeat replay and MITM attacks with 12s window."""
        nonce = secrets.token_hex(16)
        server_challenge = secrets.token_hex(16)
        expires_at = int(time.time()) + 12 # Tight 12-second handshake window
        
        # Derive unique session encryption key locally (never sent to client in verify response)
        session_key = CryptoEngine.derive_session_key(
            client_challenge=client_challenge,
            server_challenge=server_challenge,
            nonce=nonce,
            license_key=license_key,
            hwid=hwid
        )

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
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifies that the executor client mathematically signed the challenge with HWID & Key.
        Returns (is_valid, matching_hwid_representation).
        """
        client_sig_clean = client_signature.strip().lower()

        # Candidates for HWID field in signature
        candidates = [hwid]
        if raw_hwid:
            candidates.append(raw_hwid)
            candidates.append(CryptoEngine.normalize_hwid(raw_hwid))

        for cand in candidates:
            if not cand:
                continue
            # SHA256 signature ONLY. The previous 32-bit FNV-1a fallback was
            # trivially forgeable (a 4-byte space can be brute-forced in
            # milliseconds), which let an attacker pass verification without the
            # real key/HWID. It has been removed. Every executor that can run
            # this loader has a SHA-256 implementation (crypt.hash), so there is
            # no legitimate need for a weak fallback.
            expected_raw = f"{client_challenge}:{server_challenge}:{nonce}:{license_key}:{cand}"
            expected_sig = hashlib.sha256(expected_raw.encode('utf-8')).hexdigest().lower()
            if hmac.compare_digest(expected_sig, client_sig_clean):
                return True, cand

        return False, None

    @staticmethod
    def encrypt_payload(source_code: str, session_key: str, nonce: str) -> Tuple[str, str]:
        """
        Encrypts the script payload with dynamic multi-round RC4/stream cipher
        with dynamic key rotation so it can be unpacked directly in-memory inside the client Luau VM.
        Returns (base64_ciphertext, hmac_auth_tag).
        """
        key_bytes = (session_key + nonce).encode('utf-8')
        data_bytes = source_code.encode('utf-8')
        
        # Stream encryption suitable for zero-dependency execution inside Roblox Lua VM
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

    @staticmethod
    def obfuscate_with_obfuscate(source_code: str, profile: str = "dense", fail_closed: bool = False) -> str:
        """
        Applies O_bfuscate 1.1 hybrid VM virtualization, register pressure optimization,
        and polymorphic string-vault protection directly to Lua/Luau source code.

        SECURITY: When fail_closed=True (used for protected scripts on the delivery
        path), any failure raises instead of silently returning the RAW source.
        Returning raw source on error would ship unprotected plaintext to the
        client -- a fail-OPEN behavior. Protected mode must fail CLOSED.
        """
        try:
            import sys
            import os
            # Ensure O_bfuscate-1.1.0/src is in sys.path
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            obf_src = os.path.join(base_dir, "O_bfuscate-1.1.0", "src")
            if obf_src not in sys.path:
                sys.path.insert(0, obf_src)

            from o_bfuscate.pipeline import obfuscate, Config

            if profile == "dense":
                cfg = Config(
                    rename_locals=True,
                    encrypt_strings=True,
                    split_numbers=True,
                    encrypt_properties=True,
                    layered_strings=True,
                    string_shards=3,
                    string_decoys=6,
                    noise=3,
                    opaque_predicates=True,
                    number_depth=5,
                    bitwise_numbers=True,
                    virtualize=True,
                )
            else:
                cfg = Config(
                    rename_locals=True,
                    encrypt_strings=True,
                    split_numbers=True,
                    encrypt_properties=True,
                    layered_strings=False,
                    string_shards=1,
                    string_decoys=0,
                    noise=1,
                    opaque_predicates=False,
                    number_depth=2,
                    bitwise_numbers=False,
                    virtualize=False,
                )

            res = obfuscate(source_code, cfg)
            if not res or not getattr(res, "source", None):
                raise RuntimeError("Obfuscation pipeline returned empty output")
            return res.source
        except Exception as e:
            if fail_closed:
                # Do NOT leak raw source. Caller must refuse to serve the payload.
                raise RuntimeError(f"Obfuscation failed under fail-closed policy: {e}")
            # Non-protected callers may fall back to source code.
            return source_code

crypto_engine = CryptoEngine()


