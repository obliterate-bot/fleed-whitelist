from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .license_server import serve
from .licensing import LicenseDatabase, decode_b64, verify_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="o-bfuscate-license", description="O_bfuscate self-hosted licensing service")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a license database")
    init.add_argument("database", type=Path)
    init.add_argument("--project", required=True)
    init.add_argument("--secret-out", type=Path, required=True, help="write the project secret used by the obfuscator")

    add = sub.add_parser("add-project", help="add or rotate a project")
    add.add_argument("database", type=Path); add.add_argument("--project", required=True); add.add_argument("--secret-out", type=Path, required=True)

    issue = sub.add_parser("issue", help="issue a license key")
    issue.add_argument("database", type=Path); issue.add_argument("--project", required=True)
    issue.add_argument("--days", type=int); issue.add_argument("--expires-at")
    issue.add_argument("--hwid"); issue.add_argument("--hwid-lock", choices=("yes", "no"))
    issue.add_argument("--label", default=""); issue.add_argument("--note", default="")

    revoke = sub.add_parser("revoke", help="revoke a license key")
    revoke.add_argument("database", type=Path); revoke.add_argument("license_key"); revoke.add_argument("--reason", default="revoked")

    reset = sub.add_parser("reset-hwid", help="clear a license HWID binding")
    reset.add_argument("database", type=Path); reset.add_argument("license_key")

    publish = sub.add_parser("publish", help="publish a build record")
    publish.add_argument("database", type=Path); publish.add_argument("--project", required=True); publish.add_argument("--build-id", required=True)
    publish.add_argument("--artifact-url"); publish.add_argument("--artifact-file", type=Path)
    publish.add_argument("--manifest", type=Path)

    project = sub.add_parser("project", help="enable or disable a project")
    project.add_argument("database", type=Path); project.add_argument("--project", required=True)
    project.add_argument("--enabled", choices=("yes", "no"))
    project.add_argument("--allow-unpublished", choices=("yes", "no"))

    release = sub.add_parser("release", help="enable or disable a release")
    release.add_argument("database", type=Path); release.add_argument("--project", required=True); release.add_argument("--build-id", required=True)
    release.add_argument("--enabled", choices=("yes", "no"), required=True)

    telemetry = sub.add_parser("telemetry", help="enable or disable aggregate event counters")
    telemetry.add_argument("database", type=Path); telemetry.add_argument("--enabled", choices=("yes", "no"), required=True)

    server = sub.add_parser("serve", help="run the HTTP resolver")
    server.add_argument("database", type=Path); server.add_argument("--host", default="127.0.0.1"); server.add_argument("--port", type=int, default=8787)

    admin = sub.add_parser("admin-token", help="show or rotate the dashboard admin token")
    admin.add_argument("database", type=Path); admin.add_argument("--rotate", action="store_true")

    verify = sub.add_parser("verify-manifest", help="verify an HMAC-signed build manifest")
    verify.add_argument("manifest", type=Path); verify.add_argument("--secret", type=Path, required=True)
    return parser


def _write_secret(path: Path, secret: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(secret)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            database = LicenseDatabase.create(args.database)
            secret = database.add_project(args.project)
            _write_secret(args.secret_out, secret)
            print(f"created {args.database}"); print(f"wrote {args.secret_out}")
            print(f"dashboard admin token: {database.admin_token()}")
        elif args.command == "add-project":
            database = LicenseDatabase.load(args.database); secret = database.add_project(args.project)
            _write_secret(args.secret_out, secret); print(f"wrote {args.secret_out}")
        elif args.command == "issue":
            database = LicenseDatabase.load(args.database)
            print(database.issue(
                args.project,
                days=args.days,
                expires_at=args.expires_at,
                hwid=args.hwid,
                hwid_lock=None if args.hwid_lock is None else args.hwid_lock == "yes",
                label=args.label,
                note=args.note,
            ))
        elif args.command == "revoke":
            database = LicenseDatabase.load(args.database)
            if not database.revoke(args.license_key, args.reason):
                print("license not found", file=sys.stderr); return 2
            print("revoked")
        elif args.command == "reset-hwid":
            database = LicenseDatabase.load(args.database)
            if not database.reset_hwid(args.license_key):
                print("license not found", file=sys.stderr); return 2
            print("reset")
        elif args.command == "publish":
            database = LicenseDatabase.load(args.database)
            manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else None
            artifact_source = args.artifact_file.read_text(encoding="utf-8") if args.artifact_file else None
            database.publish_release(
                args.project,
                args.build_id,
                artifact_url=args.artifact_url,
                artifact_source=artifact_source,
                manifest=manifest,
            )
            print("published")
        elif args.command == "project":
            if args.enabled is None and args.allow_unpublished is None:
                raise ValueError("project requires --enabled or --allow-unpublished")
            database = LicenseDatabase.load(args.database)
            if args.enabled is not None:
                database.set_project_enabled(args.project, args.enabled == "yes")
            if args.allow_unpublished is not None:
                database.set_allow_unpublished_builds(args.project, args.allow_unpublished == "yes")
            print("updated")
        elif args.command == "release":
            database = LicenseDatabase.load(args.database); database.set_release_enabled(args.project, args.build_id, args.enabled == "yes"); print("updated")
        elif args.command == "telemetry":
            database = LicenseDatabase.load(args.database); database.set_telemetry_enabled(args.enabled == "yes"); print("updated")
        elif args.command == "serve":
            database = LicenseDatabase.load(args.database)
            display_host = "localhost" if args.host in {"127.0.0.1", "0.0.0.0"} else args.host
            print(f"dashboard: http://{display_host}:{args.port}/dashboard/")
            print(f"dashboard admin token: {database.admin_token()}")
            serve(args.database, args.host, args.port)
        elif args.command == "admin-token":
            database = LicenseDatabase.load(args.database)
            print(database.rotate_admin_token() if args.rotate else database.admin_token())
        elif args.command == "verify-manifest":
            manifest = json.loads(args.manifest.read_text(encoding="utf-8")); secret = args.secret.read_bytes()
            if verify_manifest(manifest, secret):
                print("valid"); return 0
            print("invalid", file=sys.stderr); return 1
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
