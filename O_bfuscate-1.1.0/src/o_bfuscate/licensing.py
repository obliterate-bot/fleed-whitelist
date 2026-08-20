from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
from typing import Any


SCHEMA_VERSION = 2
_AUDIT_LIMIT = 250


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_b64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hwid_hash(hwid: str, secret: bytes) -> str:
    return hmac.new(secret, b"o-bfuscate-hwid\0" + hwid.encode("utf-8"), hashlib.sha256).hexdigest()


def derive_function_key(secret: bytes, project: str, build_id: str, key_id: str, function_name: str) -> bytes:
    message = f"o-bfuscate-v1\0{project}\0{build_id}\0{key_id}\0{function_name}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).digest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_manifest(manifest: dict[str, Any], secret: bytes, key_id: str = "default") -> dict[str, Any]:
    unsigned = dict(manifest)
    unsigned.pop("signature", None)
    signature = hmac.new(secret, canonical_json(unsigned), hashlib.sha256).digest()
    signed = dict(unsigned)
    signed["signature"] = {
        "algorithm": "HMAC-SHA256",
        "key_id": key_id,
        "value": _b64(signature),
    }
    return signed


def verify_manifest(manifest: dict[str, Any], secret: bytes) -> bool:
    signature = manifest.get("signature")
    if not isinstance(signature, dict) or signature.get("algorithm") != "HMAC-SHA256":
        return False
    supplied = signature.get("value")
    if not isinstance(supplied, str):
        return False
    unsigned = dict(manifest)
    unsigned.pop("signature", None)
    expected = hmac.new(secret, canonical_json(unsigned), hashlib.sha256).digest()
    try:
        return hmac.compare_digest(expected, decode_b64(supplied))
    except (ValueError, TypeError):
        return False


def _token_keystream(secret: bytes, nonce: bytes, length: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        chunks.append(
            hmac.new(
                secret,
                b"o-bfuscate-token-stream\0" + nonce + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
        )
        counter += 1
    return b"".join(chunks)[:length]


def _seal_token(token: str, secret: bytes) -> str:
    plaintext = token.encode("utf-8")
    nonce = secrets.token_bytes(16)
    stream = _token_keystream(secret, nonce, len(plaintext))
    ciphertext = bytes(left ^ right for left, right in zip(plaintext, stream, strict=True))
    tag = hmac.new(secret, b"o-bfuscate-token-seal\0" + nonce + ciphertext, hashlib.sha256).digest()
    return _b64(nonce + ciphertext + tag)


def _unseal_token(value: str, secret: bytes) -> str:
    payload = decode_b64(value)
    if len(payload) < 49:
        raise ValueError("invalid sealed license key")
    nonce, ciphertext, supplied_tag = payload[:16], payload[16:-32], payload[-32:]
    expected_tag = hmac.new(
        secret,
        b"o-bfuscate-token-seal\0" + nonce + ciphertext,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected_tag, supplied_tag):
        raise ValueError("invalid sealed license key")
    stream = _token_keystream(secret, nonce, len(ciphertext))
    return bytes(left ^ right for left, right in zip(ciphertext, stream, strict=True)).decode("utf-8")


def _public_release(release: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(release, dict):
        return None
    return {
        "build_id": release.get("build_id"),
        "artifact_url": release.get("artifact_url"),
        "manifest": release.get("manifest"),
        "enabled": release.get("enabled", True),
        "published_at": release.get("published_at"),
    }


@dataclass(slots=True)
class ResolveResult:
    allowed: bool
    reason: str
    function_key: bytes | None = None
    expires_at: str | None = None
    release: dict[str, Any] | None = None


class LicenseDatabase:
    """Small self-hosted JSON license database.

    License verification uses one-way SHA-256 hashes. New records also retain an
    authenticated encrypted copy so an authenticated dashboard operator can
    reveal a key or generate a loader without replacing it. HWIDs are always
    stored as keyed hashes.
    """

    def __init__(self, path: Path, data: dict[str, Any]) -> None:
        self.path = path
        self.data = data

    @classmethod
    def create(cls, path: Path) -> LicenseDatabase:
        data: dict[str, Any] = {
            "schema": SCHEMA_VERSION,
            "created_at": _iso(_utc_now()),
            "service_secret": _b64(secrets.token_bytes(32)),
            "admin_secret": _b64(secrets.token_bytes(32)),
            "projects": {},
            "licenses": {},
            "telemetry": {"enabled": False, "events": {}},
            "stats": {
                "successful_authorizations": 0,
                "denied_authorizations": 0,
                "loader_requests": 0,
            },
            "audit": [],
        }
        database = cls(path, data)
        database.save()
        return database

    @classmethod
    def load(cls, path: Path) -> LicenseDatabase:
        data = json.loads(path.read_text(encoding="utf-8"))
        schema = data.get("schema")
        if schema == 1:
            cls._migrate_v1(data)
            database = cls(path, data)
            database.save()
            return database
        if schema != SCHEMA_VERSION:
            raise ValueError(f"unsupported license database schema: {schema!r}")
        return cls(path, data)

    @staticmethod
    def _migrate_v1(data: dict[str, Any]) -> None:
        data["schema"] = SCHEMA_VERSION
        data.setdefault("admin_secret", _b64(secrets.token_bytes(32)))
        data.setdefault(
            "stats",
            {
                "successful_authorizations": 0,
                "denied_authorizations": 0,
                "loader_requests": 0,
            },
        )
        data.setdefault("audit", [])
        for digest, record in data.get("licenses", {}).items():
            if not isinstance(record, dict):
                continue
            record.setdefault("id", f"lic_{digest[:16]}")
            record.setdefault("label", "")
            record.setdefault("note", "")
            record.setdefault("key_prefix", None)
            record.setdefault("key_suffix", None)
            record.setdefault("sealed_key", None)
            # None preserves the v1 policy: optional on first use, then bound
            # whenever a client supplies a HWID.
            record.setdefault("hwid_lock", None)
            record.setdefault("hwid_bound_at", record.get("last_seen_at") if record.get("hwid_hash") else None)
            record.setdefault("hwid_reset_count", 0)
            record.setdefault("updated_at", record.get("created_at"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(self.path)

    def _service_secret(self) -> bytes:
        return decode_b64(self.data["service_secret"])

    def admin_token(self) -> str:
        return "obfa_" + self.data["admin_secret"]

    def verify_admin_token(self, supplied: str) -> bool:
        return hmac.compare_digest(self.admin_token(), supplied)

    def rotate_admin_token(self) -> str:
        self.data["admin_secret"] = _b64(secrets.token_bytes(32))
        self._audit("admin_token_rotated")
        self.save()
        return self.admin_token()

    def _hwid_hash(self, hwid: str) -> str:
        return hwid_hash(hwid, self._service_secret())

    def _audit(
        self,
        action: str,
        *,
        license_id: str | None = None,
        project: str | None = None,
        detail: str | None = None,
    ) -> None:
        events = self.data.setdefault("audit", [])
        events.append(
            {
                "action": action,
                "license_id": license_id,
                "project": project,
                "detail": detail,
                "at": _iso(_utc_now()),
            }
        )
        if len(events) > _AUDIT_LIMIT:
            del events[:-_AUDIT_LIMIT]

    def _count_authorization(self, allowed: bool, *, loader: bool = False) -> None:
        stats = self.data.setdefault("stats", {})
        field = "successful_authorizations" if allowed else "denied_authorizations"
        stats[field] = int(stats.get(field, 0)) + 1
        if loader:
            stats["loader_requests"] = int(stats.get("loader_requests", 0)) + 1

    def add_project(self, project: str, *, secret: bytes | None = None) -> bytes:
        if not project or any(
            ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for ch in project
        ):
            raise ValueError("project id contains unsupported characters")
        secret = secret or secrets.token_bytes(32)
        projects = self.data.setdefault("projects", {})
        existing = projects.get(project)
        if isinstance(existing, dict):
            existing["secret"] = _b64(secret)
            existing["rotated_at"] = _iso(_utc_now())
            existing.setdefault("allow_unpublished_builds", False)
        else:
            projects[project] = {
                "secret": _b64(secret),
                "enabled": True,
                "created_at": _iso(_utc_now()),
                "latest_release": None,
                "releases": {},
                "allow_unpublished_builds": False,
            }
        self._audit("project_saved", project=project)
        self.save()
        return secret

    def project_secret(self, project: str) -> bytes:
        record = self.data.get("projects", {}).get(project)
        if not isinstance(record, dict):
            raise KeyError(f"unknown project: {project}")
        return decode_b64(record["secret"])

    def set_project_enabled(self, project: str, enabled: bool) -> None:
        record = self.data.get("projects", {}).get(project)
        if not isinstance(record, dict):
            raise KeyError(f"unknown project: {project}")
        record["enabled"] = bool(enabled)
        self._audit("project_enabled" if enabled else "project_disabled", project=project)
        self.save()

    def set_allow_unpublished_builds(self, project: str, enabled: bool) -> None:
        record = self.data.get("projects", {}).get(project)
        if not isinstance(record, dict):
            raise KeyError(f"unknown project: {project}")
        record["allow_unpublished_builds"] = bool(enabled)
        self.save()

    def _new_license_id(self) -> str:
        used = {
            record.get("id")
            for record in self.data.get("licenses", {}).values()
            if isinstance(record, dict)
        }
        while True:
            candidate = "lic_" + _b64(secrets.token_bytes(9))
            if candidate not in used:
                return candidate

    def issue(
        self,
        project: str,
        *,
        days: int | None = None,
        expires_at: str | datetime | None = None,
        hwid: str | None = None,
        hwid_lock: bool | None = None,
        label: str = "",
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if project not in self.data.get("projects", {}):
            raise KeyError(f"unknown project: {project}")
        if days is not None and expires_at is not None:
            raise ValueError("use either days or expires_at, not both")
        if days is not None and days <= 0:
            raise ValueError("license duration must be a positive number of days")
        if len(label) > 120:
            raise ValueError("license label is too long")
        if len(note) > 1000:
            raise ValueError("license note is too long")
        expiry: datetime | None
        if isinstance(expires_at, str):
            expiry = _parse_time(expires_at)
        elif isinstance(expires_at, datetime):
            expiry = expires_at.astimezone(timezone.utc)
        else:
            expiry = _utc_now() + timedelta(days=days) if days is not None else None
        token = "obf1_" + _b64(secrets.token_bytes(24))
        license_id = self._new_license_id()
        # None is the compatibility policy used by the original CLI. The
        # dashboard passes an explicit boolean and defaults to strict locking.
        enforce_hwid = None if hwid_lock is None else bool(hwid_lock)
        now = _iso(_utc_now())
        self.data.setdefault("licenses", {})[token_hash(token)] = {
            "id": license_id,
            "project": project,
            "label": label.strip(),
            "note": note.strip(),
            "created_at": now,
            "updated_at": now,
            "expires_at": _iso(expiry),
            "revoked": False,
            "hwid_lock": enforce_hwid,
            "hwid_hash": self._hwid_hash(hwid) if hwid else None,
            "hwid_bound_at": now if hwid else None,
            "hwid_reset_count": 0,
            "metadata": metadata or {},
            "last_seen_at": None,
            "key_prefix": token[:11],
            "key_suffix": token[-5:],
            "sealed_key": _seal_token(token, self._service_secret()),
        }
        self._audit("license_issued", license_id=license_id, project=project, detail=label.strip() or None)
        self.save()
        return token

    def _find_license(self, identifier: str) -> tuple[str, dict[str, Any]] | None:
        licenses = self.data.get("licenses", {})
        direct = licenses.get(token_hash(identifier))
        if isinstance(direct, dict):
            return token_hash(identifier), direct
        for digest, record in licenses.items():
            if isinstance(record, dict) and record.get("id") == identifier:
                return digest, record
        return None

    def reveal_key(self, identifier: str) -> str | None:
        found = self._find_license(identifier)
        if found is None:
            return None
        _digest, record = found
        sealed = record.get("sealed_key")
        if not isinstance(sealed, str):
            return None
        return _unseal_token(sealed, self._service_secret())

    def revoke(self, identifier: str, reason: str = "revoked") -> bool:
        found = self._find_license(identifier)
        if found is None:
            return False
        _digest, record = found
        record["revoked"] = True
        record["revocation_reason"] = reason[:240]
        record["updated_at"] = _iso(_utc_now())
        self._audit(
            "license_revoked",
            license_id=record.get("id"),
            project=record.get("project"),
            detail=reason[:240],
        )
        self.save()
        return True

    def restore(self, identifier: str) -> bool:
        found = self._find_license(identifier)
        if found is None:
            return False
        _digest, record = found
        record["revoked"] = False
        record.pop("revocation_reason", None)
        record["updated_at"] = _iso(_utc_now())
        self._audit(
            "license_restored",
            license_id=record.get("id"),
            project=record.get("project"),
        )
        self.save()
        return True

    def reset_hwid(self, identifier: str) -> bool:
        found = self._find_license(identifier)
        if found is None:
            return False
        _digest, record = found
        record["hwid_hash"] = None
        record["hwid_bound_at"] = None
        record["hwid_reset_count"] = int(record.get("hwid_reset_count", 0)) + 1
        record["updated_at"] = _iso(_utc_now())
        self._audit(
            "hwid_reset",
            license_id=record.get("id"),
            project=record.get("project"),
        )
        self.save()
        return True

    def set_hwid_lock(self, identifier: str, enabled: bool) -> bool:
        found = self._find_license(identifier)
        if found is None:
            return False
        _digest, record = found
        record["hwid_lock"] = bool(enabled)
        record["updated_at"] = _iso(_utc_now())
        self._audit(
            "hwid_lock_enabled" if enabled else "hwid_lock_disabled",
            license_id=record.get("id"),
            project=record.get("project"),
        )
        self.save()
        return True

    def set_expiration(self, identifier: str, expires_at: str | datetime | None) -> bool:
        found = self._find_license(identifier)
        if found is None:
            return False
        _digest, record = found
        if isinstance(expires_at, str):
            expiry = _parse_time(expires_at)
        elif isinstance(expires_at, datetime):
            expiry = expires_at.astimezone(timezone.utc)
        else:
            expiry = None
        record["expires_at"] = _iso(expiry)
        record["updated_at"] = _iso(_utc_now())
        self._audit(
            "expiration_updated",
            license_id=record.get("id"),
            project=record.get("project"),
            detail=_iso(expiry) or "never",
        )
        self.save()
        return True

    def publish_release(
        self,
        project: str,
        build_id: str,
        *,
        artifact_url: str | None = None,
        artifact_source: str | None = None,
        manifest: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        record = self.data.get("projects", {}).get(project)
        if not isinstance(record, dict):
            raise KeyError(f"unknown project: {project}")
        if not build_id or len(build_id) > 120:
            raise ValueError("invalid build id")
        if artifact_source is not None and len(artifact_source.encode("utf-8")) > 5 * 1024 * 1024:
            raise ValueError("inline artifact exceeds 5 MiB")
        if artifact_url is not None and len(artifact_url) > 2048:
            raise ValueError("artifact URL is too long")
        release = {
            "build_id": build_id,
            "artifact_url": artifact_url or None,
            "artifact_source": artifact_source,
            "artifact_size": len(artifact_source.encode("utf-8")) if artifact_source is not None else None,
            "manifest": manifest,
            "enabled": enabled,
            "published_at": _iso(_utc_now()),
        }
        record.setdefault("releases", {})[build_id] = release
        record["latest_release"] = build_id
        self._audit("release_published", project=project, detail=build_id)
        self.save()

    def set_release_enabled(self, project: str, build_id: str, enabled: bool) -> None:
        record = self.data.get("projects", {}).get(project)
        if not isinstance(record, dict):
            raise KeyError(f"unknown project: {project}")
        release = record.get("releases", {}).get(build_id)
        if not isinstance(release, dict):
            raise KeyError(f"unknown release: {build_id}")
        release["enabled"] = bool(enabled)
        self._audit(
            "release_enabled" if enabled else "release_disabled",
            project=project,
            detail=build_id,
        )
        self.save()

    def _authorize(
        self,
        *,
        license_key: str,
        project: str,
        hwid: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], datetime | None] | ResolveResult:
        project_record = self.data.get("projects", {}).get(project)
        if not isinstance(project_record, dict):
            return ResolveResult(False, "unknown_project")
        if not project_record.get("enabled", True):
            return ResolveResult(False, "project_disabled")
        license_record = self.data.get("licenses", {}).get(token_hash(license_key))
        if not isinstance(license_record, dict) or license_record.get("project") != project:
            return ResolveResult(False, "invalid_license")
        if license_record.get("revoked"):
            return ResolveResult(False, "revoked")
        expiry = _parse_time(license_record.get("expires_at"))
        if expiry is not None and expiry <= _utc_now():
            return ResolveResult(False, "expired", expires_at=_iso(expiry))
        stored_hwid = license_record.get("hwid_hash")
        enforce_hwid = license_record.get("hwid_lock")
        if enforce_hwid:
            if not hwid:
                return ResolveResult(False, "hwid_required", expires_at=_iso(expiry))
            if stored_hwid and not hmac.compare_digest(stored_hwid, self._hwid_hash(hwid)):
                return ResolveResult(False, "hwid_mismatch", expires_at=_iso(expiry))
            if not stored_hwid:
                license_record["hwid_hash"] = self._hwid_hash(hwid)
                license_record["hwid_bound_at"] = _iso(_utc_now())
                self._audit(
                    "hwid_bound",
                    license_id=license_record.get("id"),
                    project=project,
                )
        elif enforce_hwid is None:
            # Compatibility behavior for a pre-dashboard schema.
            if stored_hwid:
                if not hwid or not hmac.compare_digest(stored_hwid, self._hwid_hash(hwid)):
                    return ResolveResult(False, "hwid_mismatch", expires_at=_iso(expiry))
            elif hwid:
                license_record["hwid_hash"] = self._hwid_hash(hwid)
                license_record["hwid_bound_at"] = _iso(_utc_now())
        license_record["last_seen_at"] = _iso(_utc_now())
        license_record["updated_at"] = _iso(_utc_now())
        return project_record, license_record, expiry

    def _denied(self, result: ResolveResult, *, loader: bool = False) -> ResolveResult:
        self._count_authorization(False, loader=loader)
        self.save()
        return result

    def authorize(
        self,
        *,
        license_key: str,
        project: str,
        hwid: str | None = None,
    ) -> ResolveResult:
        authorized = self._authorize(license_key=license_key, project=project, hwid=hwid)
        if isinstance(authorized, ResolveResult):
            return self._denied(authorized)
        _project_record, _license_record, expiry = authorized
        self._count_authorization(True)
        self.save()
        return ResolveResult(True, "ok", expires_at=_iso(expiry))

    def resolve(
        self,
        *,
        license_key: str,
        project: str,
        build_id: str,
        key_id: str,
        function_name: str,
        hwid: str | None = None,
    ) -> ResolveResult:
        authorized = self._authorize(license_key=license_key, project=project, hwid=hwid)
        if isinstance(authorized, ResolveResult):
            return self._denied(authorized)
        project_record, _license_record, expiry = authorized
        release = project_record.get("releases", {}).get(build_id)
        if not isinstance(release, dict):
            if not project_record.get("allow_unpublished_builds", False):
                return self._denied(
                    ResolveResult(False, "release_not_found", expires_at=_iso(expiry))
                )
            release = None
        elif not release.get("enabled", True):
            return self._denied(
                ResolveResult(
                    False,
                    "release_disabled",
                    expires_at=_iso(expiry),
                    release=_public_release(release),
                )
            )
        secret = decode_b64(project_record["secret"])
        function_key = derive_function_key(secret, project, build_id, key_id, function_name)
        self._count_authorization(True)
        self.save()
        return ResolveResult(True, "ok", function_key, _iso(expiry), _public_release(release))

    def _select_release(
        self,
        project_record: dict[str, Any],
        build_id: str | None,
        expiry: datetime | None,
    ) -> ResolveResult | dict[str, Any]:
        selected = build_id or project_record.get("latest_release")
        if not isinstance(selected, str) or not selected:
            return ResolveResult(False, "no_release", expires_at=_iso(expiry))
        release = project_record.get("releases", {}).get(selected)
        if not isinstance(release, dict):
            return ResolveResult(False, "release_not_found", expires_at=_iso(expiry))
        if not release.get("enabled", True):
            return ResolveResult(
                False,
                "release_disabled",
                expires_at=_iso(expiry),
                release=_public_release(release),
            )
        return release

    def latest_release(
        self,
        *,
        license_key: str,
        project: str,
        hwid: str | None = None,
        build_id: str | None = None,
    ) -> ResolveResult:
        authorized = self._authorize(license_key=license_key, project=project, hwid=hwid)
        if isinstance(authorized, ResolveResult):
            return self._denied(authorized)
        project_record, _license_record, expiry = authorized
        release = self._select_release(project_record, build_id, expiry)
        if isinstance(release, ResolveResult):
            return self._denied(release)
        self._count_authorization(True)
        self.save()
        return ResolveResult(True, "ok", expires_at=_iso(expiry), release=_public_release(release))

    def loader_release(
        self,
        *,
        license_key: str,
        project: str,
        hwid: str | None = None,
        build_id: str | None = None,
    ) -> ResolveResult:
        authorized = self._authorize(license_key=license_key, project=project, hwid=hwid)
        if isinstance(authorized, ResolveResult):
            return self._denied(authorized, loader=True)
        project_record, _license_record, expiry = authorized
        release = self._select_release(project_record, build_id, expiry)
        if isinstance(release, ResolveResult):
            return self._denied(release, loader=True)
        self._count_authorization(True, loader=True)
        self.save()
        return ResolveResult(True, "ok", expires_at=_iso(expiry), release=release)

    def set_telemetry_enabled(self, enabled: bool) -> None:
        telemetry = self.data.setdefault("telemetry", {"enabled": False, "events": {}})
        telemetry["enabled"] = bool(enabled)
        self.save()

    def record_event(
        self,
        *,
        license_key: str,
        project: str,
        event: str,
        hwid: str | None = None,
    ) -> ResolveResult:
        telemetry = self.data.setdefault("telemetry", {"enabled": False, "events": {}})
        if not telemetry.get("enabled", False):
            return ResolveResult(False, "telemetry_disabled")
        authorized = self._authorize(license_key=license_key, project=project, hwid=hwid)
        if isinstance(authorized, ResolveResult):
            return self._denied(authorized)
        if not event or len(event) > 64:
            return ResolveResult(False, "invalid_event")
        key = f"{project}:{event}"
        events = telemetry.setdefault("events", {})
        events[key] = int(events.get(key, 0)) + 1
        self.save()
        _project_record, _license_record, expiry = authorized
        return ResolveResult(True, "ok", expires_at=_iso(expiry))

    def _license_summary(self, record: dict[str, Any]) -> dict[str, Any]:
        expiry = _parse_time(record.get("expires_at"))
        if record.get("revoked"):
            status = "revoked"
        elif expiry is not None and expiry <= _utc_now():
            status = "expired"
        else:
            status = "active"
        prefix = record.get("key_prefix")
        suffix = record.get("key_suffix")
        if isinstance(prefix, str) and isinstance(suffix, str):
            key_hint = f"{prefix}••••••{suffix}"
        else:
            key_hint = "Legacy key · unavailable"
        hwid_value = record.get("hwid_hash")
        return {
            "id": record.get("id"),
            "project": record.get("project"),
            "label": record.get("label") or "",
            "note": record.get("note") or "",
            "key_hint": key_hint,
            "recoverable": isinstance(record.get("sealed_key"), str),
            "status": status,
            "revoked": bool(record.get("revoked")),
            "revocation_reason": record.get("revocation_reason"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "expires_at": record.get("expires_at"),
            "last_seen_at": record.get("last_seen_at"),
            "hwid_lock": bool(record.get("hwid_lock")),
            "hwid_bound": isinstance(hwid_value, str) and bool(hwid_value),
            "hwid_fingerprint": hwid_value[:10] if isinstance(hwid_value, str) else None,
            "hwid_bound_at": record.get("hwid_bound_at"),
            "hwid_reset_count": int(record.get("hwid_reset_count", 0)),
            "metadata": record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
        }

    def list_licenses(
        self,
        *,
        project: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        values = [
            self._license_summary(record)
            for record in self.data.get("licenses", {}).values()
            if isinstance(record, dict)
        ]
        if project:
            values = [value for value in values if value["project"] == project]
        if status and status != "all":
            values = [value for value in values if value["status"] == status]
        if search:
            needle = search.casefold()
            values = [
                value
                for value in values
                if needle
                in " ".join(
                    str(value.get(field) or "")
                    for field in ("id", "label", "key_hint", "project", "note")
                ).casefold()
            ]
        return sorted(values, key=lambda value: value.get("created_at") or "", reverse=True)

    def list_projects(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        licenses = self.list_licenses()
        for project_id, record in self.data.get("projects", {}).items():
            if not isinstance(record, dict):
                continue
            release_values = []
            for release in record.get("releases", {}).values():
                if not isinstance(release, dict):
                    continue
                delivery = (
                    "inline"
                    if isinstance(release.get("artifact_source"), str)
                    else "remote"
                    if release.get("artifact_url")
                    else "missing"
                )
                release_values.append(
                    {
                        "build_id": release.get("build_id"),
                        "enabled": release.get("enabled", True),
                        "published_at": release.get("published_at"),
                        "artifact_url": release.get("artifact_url"),
                        "artifact_size": release.get("artifact_size"),
                        "delivery": delivery,
                    }
                )
            release_values.sort(key=lambda value: value.get("published_at") or "", reverse=True)
            project_licenses = [value for value in licenses if value["project"] == project_id]
            result.append(
                {
                    "id": project_id,
                    "enabled": record.get("enabled", True),
                    "created_at": record.get("created_at"),
                    "latest_release": record.get("latest_release"),
                    "allow_unpublished_builds": record.get("allow_unpublished_builds", False),
                    "license_count": len(project_licenses),
                    "active_license_count": sum(
                        1 for value in project_licenses if value["status"] == "active"
                    ),
                    "releases": release_values,
                }
            )
        return sorted(result, key=lambda value: value["id"].casefold())

    def overview(self) -> dict[str, Any]:
        licenses = self.list_licenses()
        status_counts = {
            name: sum(1 for value in licenses if value["status"] == name)
            for name in ("active", "expired", "revoked")
        }
        now = _utc_now()
        expiring_soon = 0
        for value in licenses:
            expiry = _parse_time(value.get("expires_at"))
            if value["status"] == "active" and expiry is not None and expiry <= now + timedelta(days=7):
                expiring_soon += 1
        return {
            "totals": {
                "licenses": len(licenses),
                **status_counts,
                "hwid_bound": sum(1 for value in licenses if value["hwid_bound"]),
                "expiring_soon": expiring_soon,
                "projects": len(self.data.get("projects", {})),
            },
            "stats": dict(self.data.get("stats", {})),
            "recent_licenses": licenses[:6],
            "activity": list(reversed(self.data.get("audit", [])[-10:])),
            "telemetry_enabled": bool(self.data.get("telemetry", {}).get("enabled", False)),
        }
