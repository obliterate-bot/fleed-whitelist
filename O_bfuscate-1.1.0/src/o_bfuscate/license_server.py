from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
import json
from pathlib import Path
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlsplit
from urllib.request import Request, urlopen

from .licensing import LicenseDatabase, _b64, canonical_json


_MAX_BODY = 5 * 1024 * 1024
_DASHBOARD_FILES = {
    "/dashboard/": ("index.html", "text/html; charset=utf-8"),
    "/dashboard/index.html": ("index.html", "text/html; charset=utf-8"),
    "/dashboard/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/dashboard/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


def _lua_string(value: str) -> str:
    return (
        '"'
        + value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        + '"'
    )


def build_loader_source(
    *,
    base_url: str,
    project: str,
    license_key: str,
    hwid_lock: bool,
    build_id: str | None = None,
) -> tuple[str, str, str]:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute http(s) URL")
    root = base_url.rstrip("/")
    endpoint = (
        f"{root}/v1/loader/{quote(project, safe='')}?"
        f"key={quote(license_key, safe='')}"
    )
    if build_id:
        endpoint += f"&build_id={quote(build_id, safe='')}"
    if hwid_lock:
        code = "\n".join(
            [
                'local HttpService = game:GetService("HttpService")',
                'local Analytics = game:GetService("RbxAnalyticsService")',
                "local hwid = Analytics:GetClientId()",
                f"local endpoint = {_lua_string(endpoint + '&hwid=')}",
                "local source = game:HttpGet(endpoint .. HttpService:UrlEncode(hwid))",
                "local chunk, compileError = loadstring(source)",
                'assert(chunk, compileError or "O_bfuscate loader compilation failed")',
                "return chunk()",
            ]
        )
        one_liner = (
            "loadstring(game:HttpGet("
            + _lua_string(endpoint + "&hwid=")
            + '..game:GetService("HttpService"):UrlEncode('
            + 'game:GetService("RbxAnalyticsService"):GetClientId())))()'
        )
    else:
        code = "\n".join(
            [
                f"local source = game:HttpGet({_lua_string(endpoint)})",
                "local chunk, compileError = loadstring(source)",
                'assert(chunk, compileError or "O_bfuscate loader compilation failed")',
                "return chunk()",
            ]
        )
        one_liner = f"loadstring(game:HttpGet({_lua_string(endpoint)}))()"
    return code, one_liner, endpoint


class LicenseRequestHandler(BaseHTTPRequestHandler):
    database_path: Path
    database_lock = threading.Lock()
    server_version = "O_bfuscate"
    sys_version = ""

    def _send(
        self,
        status: int,
        payload: bytes,
        content_type: str,
        *,
        dashboard: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if dashboard:
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'",
            )
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, value: Any) -> None:
        self._send(status, canonical_json(value), "application/json; charset=utf-8")

    def _text(self, status: int, value: str, *, content_type: str = "text/plain; charset=utf-8") -> None:
        self._send(status, value.encode("utf-8"), content_type)

    def _redirect(self, location: str) -> None:
        self._send(
            HTTPStatus.FOUND,
            b"",
            "text/plain; charset=utf-8",
            extra_headers={"Location": location},
        )

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > _MAX_BODY:
            raise ValueError("invalid body length")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    def _bearer_token(self) -> str | None:
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            return authorization[7:].strip()
        token = self.headers.get("X-Admin-Token")
        return token.strip() if token else None

    def _admin_database(self) -> LicenseDatabase | None:
        database = LicenseDatabase.load(self.database_path)
        supplied = self._bearer_token()
        if not supplied or not database.verify_admin_token(supplied):
            self._json(
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "reason": "admin_auth_required"},
            )
            return None
        return database

    def _serve_dashboard(self, path: str) -> None:
        item = _DASHBOARD_FILES.get(path)
        if item is None:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not_found"})
            return
        filename, content_type = item
        payload = (
            resources.files("o_bfuscate")
            .joinpath("dashboard", filename)
            .read_bytes()
        )
        self._send(HTTPStatus.OK, payload, content_type, dashboard=True)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/":
            self._redirect("/dashboard/")
            return
        if path == "/health":
            self._json(
                HTTPStatus.OK,
                {"ok": True, "service": "O_bfuscate licensing", "version": 2},
            )
            return
        if path == "/favicon.ico":
            self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon", dashboard=True)
            return
        if path in _DASHBOARD_FILES:
            self._serve_dashboard(path)
            return
        if path == "/dashboard":
            self._redirect("/dashboard/")
            return
        if path.startswith("/api/admin/"):
            self._handle_admin_get(path, parse_qs(parsed.query))
            return
        if path.startswith("/v1/loader/"):
            self._handle_loader_get(path, parse_qs(parsed.query))
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not_found"})

    def _handle_admin_get(self, path: str, query: dict[str, list[str]]) -> None:
        with self.database_lock:
            database = self._admin_database()
            if database is None:
                return
            if path == "/api/admin/session":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "O_bfuscate Keyauth",
                        "database": self.database_path.name,
                    },
                )
                return
            if path == "/api/admin/overview":
                self._json(HTTPStatus.OK, {"ok": True, **database.overview()})
                return
            if path == "/api/admin/projects":
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "projects": database.list_projects()},
                )
                return
            if path == "/api/admin/licenses":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "licenses": database.list_licenses(
                            project=query.get("project", [None])[0],
                            status=query.get("status", [None])[0],
                            search=query.get("search", [None])[0],
                        ),
                    },
                )
                return
            prefix = "/api/admin/licenses/"
            if path.startswith(prefix) and path.endswith("/key"):
                license_id = unquote(path[len(prefix) : -len("/key")]).strip("/")
                license_key = database.reveal_key(license_id)
                if license_key is None:
                    self._json(
                        HTTPStatus.NOT_FOUND,
                        {"ok": False, "reason": "key_not_recoverable"},
                    )
                    return
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "license_id": license_id, "license_key": license_key},
                )
                return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not_found"})

    def _handle_loader_get(self, path: str, query: dict[str, list[str]]) -> None:
        project = unquote(path[len("/v1/loader/") :]).strip("/")
        license_key = query.get("key", [""])[0]
        hwid = query.get("hwid", [None])[0]
        build_id = query.get("build_id", [None])[0]
        if not project or not license_key:
            self._text(
                HTTPStatus.BAD_REQUEST,
                'error("O_bfuscate loader: missing project or license key", 0)',
            )
            return
        with self.database_lock:
            database = LicenseDatabase.load(self.database_path)
            result = database.loader_release(
                license_key=license_key,
                project=project,
                hwid=hwid,
                build_id=build_id,
            )
        if not result.allowed or not isinstance(result.release, dict):
            reason = result.reason.replace('"', "")
            self._text(
                HTTPStatus.FORBIDDEN,
                f'error("O_bfuscate license denied: {reason}", 0)',
            )
            return
        source = result.release.get("artifact_source")
        if isinstance(source, str):
            self._text(HTTPStatus.OK, source)
            return
        artifact_url = result.release.get("artifact_url")
        if not isinstance(artifact_url, str) or not artifact_url:
            self._text(
                HTTPStatus.NOT_FOUND,
                'error("O_bfuscate loader: release has no artifact", 0)',
            )
            return
        self._proxy_artifact(artifact_url)

    def _proxy_artifact(self, artifact_url: str) -> None:
        parsed = urlsplit(artifact_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self._text(
                HTTPStatus.BAD_GATEWAY,
                'error("O_bfuscate loader: invalid artifact URL", 0)',
            )
            return
        request = Request(
            artifact_url,
            headers={"User-Agent": "O_bfuscate-Keyauth/2"},
        )
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310 - admin-configured URL
                final = urlsplit(response.geturl())
                if final.scheme not in {"http", "https"}:
                    raise ValueError("unsupported artifact redirect")
                payload = response.read(_MAX_BODY + 1)
                if len(payload) > _MAX_BODY:
                    raise ValueError("artifact exceeds 5 MiB")
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            self._text(
                HTTPStatus.BAD_GATEWAY,
                'error("O_bfuscate loader: artifact is unavailable", 0)',
            )
            return
        self._send(HTTPStatus.OK, payload, "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        try:
            body = self._body()
            if parsed.path.startswith("/api/admin/"):
                self._handle_admin_post(parsed.path, body)
                return
            with self.database_lock:
                database = LicenseDatabase.load(self.database_path)
                self._handle_public_post(database, parsed.path, body)
        except (ValueError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "bad_request", "detail": str(exc)},
            )

    def _handle_admin_post(self, path: str, body: dict[str, Any]) -> None:
        with self.database_lock:
            database = self._admin_database()
            if database is None:
                return
            if path == "/api/admin/licenses":
                project = body.get("project")
                if not isinstance(project, str):
                    raise ValueError("project is required")
                days = body.get("days")
                if days is not None and not isinstance(days, int):
                    raise ValueError("days must be an integer")
                expires_at = body.get("expires_at")
                if expires_at is not None and not isinstance(expires_at, str):
                    raise ValueError("expires_at must be an ISO date")
                hwid = body.get("hwid")
                if hwid is not None and not isinstance(hwid, str):
                    raise ValueError("hwid must be a string")
                token = database.issue(
                    project,
                    days=days,
                    expires_at=expires_at,
                    hwid=hwid or None,
                    hwid_lock=bool(body.get("hwid_lock", True)),
                    label=str(body.get("label") or ""),
                    note=str(body.get("note") or ""),
                )
                found = database._find_license(token)
                assert found is not None
                license_id = found[1]["id"]
                summary = next(
                    value
                    for value in database.list_licenses()
                    if value["id"] == license_id
                )
                self._json(
                    HTTPStatus.CREATED,
                    {"ok": True, "license_key": token, "license": summary},
                )
                return
            if path == "/api/admin/projects":
                project = body.get("project")
                if not isinstance(project, str):
                    raise ValueError("project is required")
                secret = database.add_project(project)
                summary = next(
                    value
                    for value in database.list_projects()
                    if value["id"] == project
                )
                self._json(
                    HTTPStatus.CREATED,
                    {
                        "ok": True,
                        "project": summary,
                        "project_secret": _b64(secret),
                    },
                )
                return
            if path == "/api/admin/releases":
                project = body.get("project")
                build_id = body.get("build_id")
                if not isinstance(project, str) or not isinstance(build_id, str):
                    raise ValueError("project and build_id are required")
                artifact_url = body.get("artifact_url")
                artifact_source = body.get("artifact_source")
                if artifact_url is not None and not isinstance(artifact_url, str):
                    raise ValueError("artifact_url must be a string")
                if artifact_source is not None and not isinstance(artifact_source, str):
                    raise ValueError("artifact_source must be a string")
                if not artifact_url and not artifact_source:
                    raise ValueError("an inline artifact or artifact URL is required")
                database.publish_release(
                    project,
                    build_id,
                    artifact_url=artifact_url or None,
                    artifact_source=artifact_source or None,
                )
                self._json(
                    HTTPStatus.CREATED,
                    {"ok": True, "projects": database.list_projects()},
                )
                return
            if path == "/api/admin/loaders":
                license_id = body.get("license_id")
                base_url = body.get("base_url")
                if not isinstance(license_id, str) or not isinstance(base_url, str):
                    raise ValueError("license_id and base_url are required")
                found = database._find_license(license_id)
                if found is None:
                    raise KeyError("unknown license")
                record = found[1]
                license_key = database.reveal_key(license_id)
                if license_key is None:
                    raise ValueError("this legacy key cannot be recovered")
                build_id = body.get("build_id")
                if build_id is not None and not isinstance(build_id, str):
                    raise ValueError("build_id must be a string")
                loader, one_liner, endpoint = build_loader_source(
                    base_url=base_url,
                    project=record["project"],
                    license_key=license_key,
                    hwid_lock=bool(record.get("hwid_lock")),
                    build_id=build_id or None,
                )
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "loader": loader,
                        "one_liner": one_liner,
                        "endpoint": endpoint,
                    },
                )
                return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not_found"})

    def do_PATCH(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        prefix = "/api/admin/licenses/"
        if not parsed.path.startswith(prefix):
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not_found"})
            return
        try:
            body = self._body()
            license_id = unquote(parsed.path[len(prefix) :]).strip("/")
            with self.database_lock:
                database = self._admin_database()
                if database is None:
                    return
                action = body.get("action")
                if action == "reset_hwid":
                    updated = database.reset_hwid(license_id)
                elif action == "revoke":
                    updated = database.revoke(
                        license_id,
                        str(body.get("reason") or "revoked by dashboard"),
                    )
                elif action == "restore":
                    updated = database.restore(license_id)
                elif action == "set_hwid_lock":
                    if not isinstance(body.get("enabled"), bool):
                        raise ValueError("enabled must be a boolean")
                    updated = database.set_hwid_lock(license_id, body["enabled"])
                elif action == "set_expiration":
                    expires_at = body.get("expires_at")
                    if expires_at is not None and not isinstance(expires_at, str):
                        raise ValueError("expires_at must be an ISO date or null")
                    updated = database.set_expiration(license_id, expires_at)
                else:
                    raise ValueError("unknown license action")
                if not updated:
                    self._json(
                        HTTPStatus.NOT_FOUND,
                        {"ok": False, "reason": "license_not_found"},
                    )
                    return
                summary = next(
                    value
                    for value in database.list_licenses()
                    if value["id"] == license_id
                )
                self._json(HTTPStatus.OK, {"ok": True, "license": summary})
        except (ValueError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "bad_request", "detail": str(exc)},
            )

    def _handle_public_post(
        self,
        database: LicenseDatabase,
        path: str,
        body: dict[str, Any],
    ) -> None:
        if path == "/v1/resolve":
            required = ("license_key", "project", "build_id", "key_id", "function")
            if any(not isinstance(body.get(field), str) for field in required):
                raise ValueError("missing resolve fields")
            result = database.resolve(
                license_key=body["license_key"],
                project=body["project"],
                build_id=body["build_id"],
                key_id=body["key_id"],
                function_name=body["function"],
                hwid=body.get("hwid") if isinstance(body.get("hwid"), str) else None,
            )
            response: dict[str, Any] = {
                "ok": result.allowed,
                "reason": result.reason,
                "expires_at": result.expires_at,
                "release": result.release,
            }
            if result.function_key is not None:
                response["function_key"] = _b64(result.function_key)
            self._json(HTTPStatus.OK if result.allowed else HTTPStatus.FORBIDDEN, response)
            return
        if path == "/v1/release":
            required = ("license_key", "project")
            if any(not isinstance(body.get(field), str) for field in required):
                raise ValueError("missing release fields")
            result = database.latest_release(
                license_key=body["license_key"],
                project=body["project"],
                hwid=body.get("hwid") if isinstance(body.get("hwid"), str) else None,
                build_id=body.get("build_id") if isinstance(body.get("build_id"), str) else None,
            )
            self._json(
                HTTPStatus.OK if result.allowed else HTTPStatus.FORBIDDEN,
                {
                    "ok": result.allowed,
                    "reason": result.reason,
                    "expires_at": result.expires_at,
                    "release": result.release,
                },
            )
            return
        if path == "/v1/event":
            required = ("license_key", "project", "event")
            if any(not isinstance(body.get(field), str) for field in required):
                raise ValueError("missing event fields")
            result = database.record_event(
                license_key=body["license_key"],
                project=body["project"],
                event=body["event"],
                hwid=body.get("hwid") if isinstance(body.get("hwid"), str) else None,
            )
            status = (
                HTTPStatus.ACCEPTED
                if result.allowed
                else HTTPStatus.NOT_IMPLEMENTED
                if result.reason == "telemetry_disabled"
                else HTTPStatus.FORBIDDEN
            )
            self._json(status, {"ok": result.allowed, "reason": result.reason})
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        return


def create_server(
    database_path: Path,
    host: str = "127.0.0.1",
    port: int = 8787,
) -> ThreadingHTTPServer:
    handler = type(
        "ConfiguredLicenseHandler",
        (LicenseRequestHandler,),
        {"database_path": database_path, "database_lock": threading.Lock()},
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(
    database_path: Path,
    host: str = "127.0.0.1",
    port: int = 8787,
) -> None:
    server = create_server(database_path, host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
