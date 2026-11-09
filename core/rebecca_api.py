"""Async client for the Rebecca panel API (Marzban-compatible).

Single ``httpx.AsyncClient`` per instance, at most 5 concurrent requests,
3 retries on 5xx/429 with exponential backoff. 4xx responses raise
``RebeccaAPIError``; auth headers are never logged.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Optional

import httpx

from core.config import settings
from core.net import prefer_ipv4

logger = logging.getLogger(__name__)

GB = 1024 ** 3

# endpoint map confirmed by scripts/probe_api.py
PATH_SYSTEM = "/api/system"
PATH_USERS = "/api/users"
PATH_USER = "/api/user"
PATH_USER_ONE = "/api/user/{username}"
PATH_USER_USAGE = "/api/user/{username}/usage"
PATH_USER_RESET = "/api/user/{username}/reset"
PATH_USER_REVOKE = "/api/user/{username}/revoke_sub"


class RebeccaAPIError(Exception):
    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self.text = text
        super().__init__(f"Rebecca API error {status}: {text}")


class RebeccaClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        *,
        service_id: Optional[int] = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or settings.rebecca_base_url).rstrip("/")
        self.api_key = api_key or settings.rebecca_api_key
        self.service_id = service_id if service_id is not None else settings.rebecca_service_id
        self.timeout = timeout
        self._sem = asyncio.Semaphore(5)
        self._client: Optional[httpx.AsyncClient] = None
        # (timestamp, ok) for the last few hundred API calls, for stats screens
        self._recent: deque[tuple[float, bool]] = deque(maxlen=500)
        prefer_ipv4()

    def _record(self, ok: bool) -> None:
        self._recent.append((time.time(), ok))

    def success_rate(self, window: float = 300.0) -> Optional[float]:
        """2xx rate over the last ``window`` seconds, or None if no calls."""
        cutoff = time.time() - window
        recent = [ok for ts, ok in self._recent if ts >= cutoff]
        if not recent:
            return None
        return sum(1 for ok in recent if ok) / len(recent)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def __aenter__(self) -> "RebeccaClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        client = self._get_client()
        attempts = 3
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            delay = 0.5 * (2 ** attempt)
            start = time.perf_counter()
            try:
                async with self._sem:
                    resp = await client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                self._record(False)
                last_error = exc
                logger.warning("%s %s failed: %s", method, path, exc)
                if attempt < attempts - 1:
                    await asyncio.sleep(delay)
                    continue
                raise

            elapsed = (time.perf_counter() - start) * 1000
            logger.info("%s %s -> %s (%.0fms)", method, path, resp.status_code, elapsed)

            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                self._record(False)
                last_error = RebeccaAPIError(resp.status_code, resp.text)
                if attempt < attempts - 1:
                    retry_after = resp.headers.get("Retry-After")
                    wait = delay
                    if retry_after:
                        try:
                            wait = max(wait, float(retry_after))
                        except ValueError:
                            pass
                    logger.warning(
                        "%s %s -> %s, retrying in %.1fs", method, path, resp.status_code, wait
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RebeccaAPIError(resp.status_code, resp.text)

            if 400 <= resp.status_code < 500:
                self._record(False)
                raise RebeccaAPIError(resp.status_code, resp.text)

            self._record(True)
            return resp

        raise last_error if last_error else RebeccaAPIError(0, "request failed")

    # -- API surface --------------------------------------------------------
    async def ping(self) -> bool:
        try:
            await self._request("GET", PATH_SYSTEM)
            return True
        except (RebeccaAPIError, httpx.HTTPError):
            return False

    async def get_user(self, username: str) -> Optional[dict[str, Any]]:
        try:
            resp = await self._request("GET", PATH_USER_ONE.format(username=username))
        except RebeccaAPIError as exc:
            if exc.status == 404:
                return None
            raise
        return resp.json()

    async def get_user_usage(self, username: str) -> Optional[dict[str, Any]]:
        try:
            resp = await self._request("GET", PATH_USER_USAGE.format(username=username))
        except RebeccaAPIError as exc:
            if exc.status == 404:
                return None
            raise
        return resp.json()

    async def create_user(
        self,
        username: str,
        plan_gb: float,
        plan_days: int,
        notes: Optional[str] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "username": username,
            "service_id": self.service_id,
            "data_limit": int(plan_gb * GB),
            "expire": int(time.time()) + int(plan_days * 86400),
            "status": "active",
        }
        if notes is not None:
            payload["note"] = notes
        resp = await self._request("POST", PATH_USER, json=payload)
        return resp.json()

    async def update_user(self, username: str, **fields: Any) -> dict[str, Any]:
        resp = await self._request("PUT", PATH_USER_ONE.format(username=username), json=fields)
        return resp.json()

    async def delete_user(self, username: str) -> bool:
        try:
            await self._request("DELETE", PATH_USER_ONE.format(username=username))
            return True
        except RebeccaAPIError as exc:
            if exc.status == 404:
                return False
            raise

    async def reset_user_usage(self, username: str) -> dict[str, Any]:
        resp = await self._request("POST", PATH_USER_RESET.format(username=username))
        return resp.json()

    async def revoke_subscription(self, username: str) -> dict[str, Any]:
        resp = await self._request("POST", PATH_USER_REVOKE.format(username=username))
        return resp.json()

    async def list_users(self, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        resp = await self._request("GET", PATH_USERS, params={"offset": offset, "limit": limit})
        data = resp.json()
        if isinstance(data, dict):
            users = data.get("users", [])
        else:
            users = data
        return list(users)
