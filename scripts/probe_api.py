#!/usr/bin/env python3
"""Probe the live Rebecca panel API for every endpoint core/ depends on.

Makes exactly ONE live call per required endpoint, using the real API key,
and writes scripts/probe_results.json. A temporary user is created, exercised,
and deleted during the probe.

The panel may disable /openapi.json; the endpoint paths below are the verified
Marzban-style routes for this deployment (see scripts/openapi.json + TODO.md).

Required mappings:
    fetch user by username  GET    /api/user/{username}
    create user             POST   /api/user
    update user             PUT    /api/user/{username}
    delete user             DELETE /api/user/{username}
    list users              GET    /api/users?offset=&limit=
    get user usage          GET    /api/user/{username}/usage
    ping                    GET    /api/system

Environment: REBECCA_BASE_URL, REBECCA_API_KEY (from .env),
             REBECCA_SERVICE_ID (optional, default 1; Marzban requires a
             service on user creation — see TODO.md).

Exit code 0 only if every required endpoint returns 2xx.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "probe_results.json"
TIMEOUT = 30.0


def prefer_ipv4() -> None:
    """Drop IPv6 DNS answers: the panel host stalls on AAAA in this env."""
    import socket

    original = socket.getaddrinfo

    def ipv4_only(*args, **kwargs):
        results = original(*args, **kwargs)
        ipv4 = [r for r in results if r[0] == socket.AF_INET]
        return ipv4 or results

    socket.getaddrinfo = ipv4_only


def main() -> int:
    load_dotenv(ROOT / ".env")
    prefer_ipv4()
    base = os.getenv("REBECCA_BASE_URL", "").rstrip("/")
    key = os.getenv("REBECCA_API_KEY", "")
    service_id = int(os.getenv("REBECCA_SERVICE_ID", "1"))
    if not base or not key:
        raise SystemExit("REBECCA_BASE_URL and REBECCA_API_KEY must be set in .env")

    test_user = f"probe_{int(time.time())}"
    results: list[dict] = []
    created = False

    def record(name: str, method: str, path: str, resp: httpx.Response | None,
               error: str | None = None) -> dict:
        status = resp.status_code if resp is not None else None
        ok = bool(resp is not None and 200 <= resp.status_code < 300)
        detail = error
        if detail is None and resp is not None and not ok:
            detail = resp.text[:300]
        row = {
            "name": name,
            "method": method,
            "path": path,
            "status": status,
            "ok": ok,
            "detail": detail,
        }
        results.append(row)
        flag = "OK  " if ok else "FAIL"
        print(f"[{flag}] {method:6} {path} -> {status} {detail or ''}")
        return row

    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=base, headers=headers, timeout=TIMEOUT) as client:
        try:
            record("ping", "GET", "/api/system", client.get("/api/system"))
            record(
                "list_users",
                "GET",
                "/api/users",
                client.get("/api/users", params={"offset": 0, "limit": 10}),
            )
            create = client.post(
                "/api/user",
                json={"username": test_user, "service_id": service_id},
            )
            record("create_user", "POST", "/api/user", create)
            created = create.status_code in (200, 201)

            if created:
                record(
                    "get_user",
                    "GET",
                    f"/api/user/{test_user}",
                    client.get(f"/api/user/{test_user}"),
                )
                record(
                    "get_user_usage",
                    "GET",
                    f"/api/user/{test_user}/usage",
                    client.get(f"/api/user/{test_user}/usage"),
                )
                record(
                    "update_user",
                    "PUT",
                    f"/api/user/{test_user}",
                    client.put(f"/api/user/{test_user}", json={"status": "disabled"}),
                )
            else:
                for name in ("get_user", "get_user_usage", "update_user"):
                    record(name, "SKIP", "-", None, "create_user did not succeed")
        finally:
            if created:
                record(
                    "delete_user",
                    "DELETE",
                    f"/api/user/{test_user}",
                    client.delete(f"/api/user/{test_user}"),
                )
            else:
                record("delete_user", "SKIP", "-", None, "nothing to delete")

    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    failed = [r for r in results if not r["ok"]]
    print(f"\nwrote {OUT} ({len(results)} probes, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
