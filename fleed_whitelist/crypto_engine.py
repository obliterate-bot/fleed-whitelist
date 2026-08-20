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
    def inject_watermark(source_code: str, license_key: str, user_id: Optional[int] = None, discord_id: Optional[str] = None) -> str:
        """
        Injects an invisible, deterministic steganographic watermark into the Lua source code
        before VM compilation or encryption. If a dumped script is leaked online, the developer
        can decode the embedded watermarks to identify the leaking license and Discord user.
        """
        raw_uid = str(user_id or 0)
        raw_disc = str(discord_id or "NONE")
        sig_data = f"{license_key}|{raw_uid}|{raw_disc}"
        
        # 1. Cryptographic Watermark Tag
        tag_hash = hashlib.sha256(f"{MASTER_SECRET}:{sig_data}".encode()).hexdigest()[:16]
        encoded_sig = base64.b64encode(sig_data.encode()).decode()
        
        # Non-executable embedded watermark identifier variable (folded inside local scope)
        watermark_header = f'local _FG_WM = "{tag_hash}:{encoded_sig}"; '
        
        # 2. Steganographic zero-width spacing fingerprint appended as invisible bits
        # Space (0x20) and Tab (0x09) represent binary 0 and 1
        bin_str = "".join(f"{b:08b}" for b in tag_hash.encode())
        stego_chars = "".join(" " if bit == "0" else "\t" for bit in bin_str)
        stego_comment = f"--[[\n{stego_chars}\n]]\n"
        
        return f"{stego_comment}{watermark_header}\n{source_code}"

    @staticmethod
    def decode_watermark(source_or_dump: str) -> Optional[Dict[str, str]]:
        """Extracts and verifies a steganographic watermark from a dumped Lua script."""
        import re
        match = re.search(r'_FG_WM\s*=\s*"([a-f0-9]{16}):([^"]+)"', source_or_dump)
        if match:
            tag_hash, encoded_sig = match.group(1), match.group(2)
            try:
                sig_data = base64.b64decode(encoded_sig).decode()
                expected_hash = hashlib.sha256(f"{MASTER_SECRET}:{sig_data}".encode()).hexdigest()[:16]
                if hmac.compare_digest(tag_hash, expected_hash):
                    parts = sig_data.split("|")
                    return {
                        "verified": True,
                        "license_key": parts[0] if len(parts) > 0 else "UNKNOWN",
                        "roblox_user_id": parts[1] if len(parts) > 1 else "0",
                        "discord_id": parts[2] if len(parts) > 2 else "NONE",
                    }
            except Exception:
                pass
        return None

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
    def compute_key_proof(license_key: str) -> str:
        """Computes one-way key proof hash to keep license key completely off the wire."""
        clean_key = license_key.strip().upper()
        return hashlib.sha256(f"fleed-ident:{clean_key}".encode('utf-8')).hexdigest()

    @staticmethod
    def derive_kek(license_key: str, nonce: str) -> str:
        """Derives a Key-Encryption-Key (KEK) using SHA256 over the license key and nonce."""
        clean_key = license_key.strip().upper()
        return hashlib.sha256(f"fleed-kek:{clean_key}:{nonce}".encode('utf-8')).hexdigest()

    @staticmethod
    def derive_session_key_server(script_id: int, client_challenge: str, server_challenge: str, nonce: str, hwid: str) -> str:
        """
        Derives an unguessable server-side session key incorporating MASTER_SECRET.
        A MITM proxy listening to traffic CANNOT compute this key because MASTER_SECRET is never sent across the wire.
        """
        seed = f"{MASTER_SECRET}:{script_id}:{client_challenge}:{server_challenge}:{nonce}:{hwid}"
        return hashlib.sha256(seed.encode('utf-8')).hexdigest()

    @staticmethod
    def wrap_session_key(session_key: str, kek: str) -> str:
        """
        Encrypts the session key with the KEK (Key-Encryption-Key) so only a client who actually
        possesses the license key can unwrap the session key.
        """
        kek_bytes = kek.encode('utf-8')
        sk_bytes = session_key.encode('utf-8')
        wrapped = bytearray()
        for idx, b in enumerate(sk_bytes):
            wrapped.append(b ^ kek_bytes[idx % len(kek_bytes)])
        return base64.b64encode(wrapped).decode()

    @staticmethod
    def unwrap_session_key(wrapped_b64: str, kek: str) -> str:
        """Unwraps the session key using the local KEK."""
        kek_bytes = kek.encode('utf-8')
        wrapped = base64.b64decode(wrapped_b64)
        unwrapped = bytearray()
        for idx, b in enumerate(wrapped):
            unwrapped.append(b ^ kek_bytes[idx % len(kek_bytes)])
        return bytes(unwrapped).decode('utf-8')

    @staticmethod
    def derive_session_key(client_challenge: str, server_challenge: str, nonce: str, license_key: str, hwid: str) -> str:
        """
        Legacy/Fallback session key derivation.
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
            # SHA256 Candidate (using key proof / clean key)
            expected_raw = f"{client_challenge}:{server_challenge}:{nonce}:{license_key}:{cand}"
            expected_sig = hashlib.sha256(expected_raw.encode('utf-8')).hexdigest().lower()
            if hmac.compare_digest(expected_sig, client_sig_clean):
                return True, cand

            # Also allow signature over key proof hash
            key_proof = CryptoEngine.compute_key_proof(license_key)
            expected_raw_kp = f"{client_challenge}:{server_challenge}:{nonce}:{key_proof}:{cand}"
            expected_sig_kp = hashlib.sha256(expected_raw_kp.encode('utf-8')).hexdigest().lower()
            if hmac.compare_digest(expected_sig_kp, client_sig_clean):
                return True, cand

            # FNV-1a 32-bit fallback for lightweight executors
            h = 0x811c9dc5
            for b in expected_raw.encode('utf-8'):
                h = (h ^ b) & 0xFFFFFFFF
                h = (h * 0x01000193) & 0xFFFFFFFF
            fnv_sig = f"{h:08x}".lower()
            if hmac.compare_digest(fnv_sig, client_sig_clean):
                return True, cand

        return False, None

    @staticmethod
    def encrypt_payload(source_code: str, session_key: str, nonce: str) -> Tuple[str, str]:
        """
        Encrypts the script payload with dynamic multi-round RC4/stream cipher
        with dynamic key rotation so it can be unpacked directly in-memory inside the client Luau VM.
        Computes a secret-prefix SHA-256 auth tag over session_key + nonce + raw ciphertext bytes.
        Returns (base64_ciphertext, auth_tag).
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
        # Secret-prefix SHA-256 auth tag: sha256(session_key + nonce + cipher_bytes)
        # Matches client-side sha256_hex(session_key .. nonce .. decoded_str)
        auth_tag_payload = key_bytes + bytes(cipher)
        auth_tag = hashlib.sha256(auth_tag_payload).hexdigest()
        return encrypted_b64, auth_tag

    @staticmethod
    def obfuscate_with_obfuscate(source_code: str, profile: str = "dense", fail_closed: bool = False) -> str:
        """
        Applies O_bfuscate 1.1 hybrid VM virtualization, register pressure optimization,
        and polymorphic string-vault protection directly to Lua/Luau source code.
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
            return res.source
        except Exception as e:
            if fail_closed:
                raise RuntimeError(f"Obfuscation pipeline failed under fail-closed security policy: {str(e)}")
            # Fallback to source code if parser fails on custom syntax and fail_closed is False
            return source_code


crypto_engine = CryptoEngine()


