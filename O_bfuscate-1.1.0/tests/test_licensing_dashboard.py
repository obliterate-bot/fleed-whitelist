from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import quote

from o_bfuscate.license_server import build_loader_source, create_server
from o_bfuscate.licensing import LicenseDatabase


class LicenseDashboardTests(unittest.TestCase):
    def test_strict_hwid_lifecycle_and_recoverable_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "licenses.json"
            database = LicenseDatabase.create(path)
            database.add_project("demo")
            token = database.issue(
                "demo",
                days=30,
                hwid_lock=True,
                label="Customer A",
            )

            self.assertTrue(database.verify_admin_token(database.admin_token()))
            self.assertEqual(database.reveal_key(token), token)
            self.assertEqual(
                database.authorize(license_key=token, project="demo").reason,
                "hwid_required",
            )
            self.assertTrue(
                database.authorize(
                    license_key=token,
                    project="demo",
                    hwid="device-one",
                ).allowed
            )
            self.assertEqual(
                database.authorize(
                    license_key=token,
                    project="demo",
                    hwid="device-two",
                ).reason,
                "hwid_mismatch",
            )

            summary = database.list_licenses()[0]
            self.assertTrue(summary["hwid_bound"])
            self.assertNotIn("device-one", path.read_text(encoding="utf-8"))
            self.assertTrue(database.reset_hwid(summary["id"]))
            self.assertTrue(
                database.authorize(
                    license_key=token,
                    project="demo",
                    hwid="device-two",
                ).allowed
            )
            self.assertEqual(database.overview()["totals"]["active"], 1)

    def test_expiration_and_legacy_optional_hwid_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "licenses.json"
            database = LicenseDatabase.create(path)
            database.add_project("demo")
            token = database.issue("demo")
            self.assertTrue(
                database.authorize(
                    license_key=token,
                    project="demo",
                    hwid="first-device",
                ).allowed
            )
            self.assertEqual(
                database.authorize(
                    license_key=token,
                    project="demo",
                    hwid="other-device",
                ).reason,
                "hwid_mismatch",
            )

            license_id = database.list_licenses()[0]["id"]
            past = datetime.now(timezone.utc) - timedelta(minutes=1)
            self.assertTrue(database.set_expiration(license_id, past))
            self.assertEqual(
                database.authorize(
                    license_key=token,
                    project="demo",
                    hwid="first-device",
                ).reason,
                "expired",
            )

    def test_loader_source_generation(self) -> None:
        readable, one_liner, endpoint = build_loader_source(
            base_url="https://keys.example.com/",
            project="demo",
            license_key="obf1_example",
            hwid_lock=True,
            build_id="v1",
        )
        self.assertIn("RbxAnalyticsService", readable)
        self.assertIn("loadstring(game:HttpGet", one_liner)
        self.assertEqual(
            endpoint,
            "https://keys.example.com/v1/loader/demo?key=obf1_example&build_id=v1",
        )

    def test_dashboard_api_and_inline_loader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "licenses.json"
            database = LicenseDatabase.create(path)
            database.add_project("demo")
            database.publish_release(
                "demo",
                "build-1",
                artifact_source='print("protected")',
            )
            token = database.issue("demo", hwid_lock=True, label="HTTP test")
            admin_token = database.admin_token()
            license_id = database.list_licenses()[0]["id"]

            server = create_server(path, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address

            def request(
                method: str,
                target: str,
                *,
                body: dict[str, object] | None = None,
                admin: bool = False,
            ) -> tuple[int, bytes, dict[str, str]]:
                connection = HTTPConnection(host, port, timeout=5)
                headers: dict[str, str] = {}
                payload = None
                if body is not None:
                    payload = json.dumps(body).encode("utf-8")
                    headers["Content-Type"] = "application/json"
                if admin:
                    headers["Authorization"] = f"Bearer {admin_token}"
                connection.request(method, target, body=payload, headers=headers)
                response = connection.getresponse()
                data = response.read()
                response_headers = dict(response.getheaders())
                status = response.status
                connection.close()
                return status, data, response_headers

            try:
                status, payload, _headers = request("GET", "/dashboard/")
                self.assertEqual(status, 200)
                self.assertIn(b"O_bfuscate Gate", payload)

                status, _payload, _headers = request("GET", "/api/admin/overview")
                self.assertEqual(status, 401)

                status, payload, _headers = request(
                    "GET",
                    "/api/admin/overview",
                    admin=True,
                )
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(payload)["totals"]["licenses"], 1)

                status, payload, _headers = request(
                    "POST",
                    "/api/admin/loaders",
                    admin=True,
                    body={
                        "license_id": license_id,
                        "base_url": f"http://{host}:{port}",
                    },
                )
                self.assertEqual(status, 200)
                self.assertIn(token, json.loads(payload)["one_liner"])

                loader_path = f"/v1/loader/demo?key={quote(token)}"
                status, payload, _headers = request("GET", loader_path)
                self.assertEqual(status, 403)
                self.assertIn(b"hwid_required", payload)

                status, payload, _headers = request(
                    "GET",
                    loader_path + "&hwid=device-a",
                )
                self.assertEqual(status, 200)
                self.assertEqual(payload, b'print("protected")')

                status, payload, _headers = request(
                    "GET",
                    loader_path + "&hwid=device-b",
                )
                self.assertEqual(status, 403)
                self.assertIn(b"hwid_mismatch", payload)

                status, payload, _headers = request(
                    "PATCH",
                    f"/api/admin/licenses/{license_id}",
                    admin=True,
                    body={"action": "reset_hwid"},
                )
                self.assertEqual(status, 200)
                self.assertFalse(json.loads(payload)["license"]["hwid_bound"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
