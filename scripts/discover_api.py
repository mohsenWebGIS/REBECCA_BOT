#!/usr/bin/env python3
"""Discover the Rebecca panel API from its OpenAPI document.

GETs {REBECCA_BASE_URL}/openapi.json, prints every path + method + summary +
request/response schema names, and saves the raw JSON to scripts/openapi.json.

Some deployments disable docs (fastapi returns {"detail": "API docs are
disabled"} with a 404). In that case this script records the raw response and
exits 0 so the caller can fall back to scripts/probe_api.py, which probes the
known Marzban-style endpoints directly.

Usage:  python scripts/discover_api.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "openapi.json"


def prefer_ipv4() -> None:
    """Drop IPv6 DNS answers: the panel host stalls on AAAA in this env."""
    import socket

    original = socket.getaddrinfo

    def ipv4_only(*args, **kwargs):
        results = original(*args, **kwargs)
        ipv4 = [r for r in results if r[0] == socket.AF_INET]
        return ipv4 or results

    socket.getaddrinfo = ipv4_only


def load_base_url() -> str:
    load_dotenv(ROOT / ".env")
    base = os.getenv("REBECCA_BASE_URL", "").rstrip("/")
    if not base:
        sys.exit("REBECCA_BASE_URL is not set (expected in .env)")
    return base


def schema_name(ref: str | None) -> str | None:
    if not ref:
        return None
    return ref.rsplit("/", 1)[-1]


def schema_names(schema: dict | None) -> list[str]:
    """Collect top-level + nested $ref schema names from a media-type schema."""
    if not schema:
        return []
    names: list[str] = []
    stack = [schema]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref:
                name = schema_name(ref)
                if name and name not in names:
                    names.append(name)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return names


def summarize(paths: dict) -> None:
    for path, methods in paths.items():
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            op = op or {}
            summary = op.get("summary") or op.get("operationId") or ""
            req = []
            body = op.get("requestBody") or {}
            for media in (body.get("content") or {}).values():
                req += schema_names(media.get("schema"))
            resp = []
            for code, r in (op.get("responses") or {}).items():
                for media in ((r or {}).get("content") or {}).values():
                    resp += schema_names(media.get("schema"))
            req_s = ", ".join(dict.fromkeys(req)) or "-"
            resp_s = ", ".join(dict.fromkeys(resp)) or "-"
            print(f"{method.upper():6} {path}\n       summary: {summary}\n       request: {req_s}\n       response: {resp_s}")


def main() -> int:
    base = load_base_url()
    prefer_ipv4()
    url = f"{base}/openapi.json"
    print(f"GET {url}")
    try:
        resp = httpx.get(url, timeout=30.0)
    except httpx.HTTPError as exc:
        sys.exit(f"request failed: {exc}")

    raw: object
    try:
        raw = resp.json()
    except ValueError:
        raw = {"_raw": resp.text}
    OUT.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"status: {resp.status_code} -> {OUT}")

    if resp.status_code != 200 or not isinstance(raw, dict) or "paths" not in raw:
        print("OpenAPI document unavailable (docs disabled?). Raw response saved.")
        print("Falling back to direct probing: run scripts/probe_api.py")
        return 0

    info = raw.get("info") or {}
    print(f"title: {info.get('title')} version: {info.get('version')}")
    summarize(raw.get("paths") or {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
