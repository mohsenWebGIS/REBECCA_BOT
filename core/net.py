"""Network helpers.

The panel host resolves to IPv6 addresses first. In some container/host
environments there is no working IPv6 route, and httpx/anyio then stalls on
the AAAA record instead of falling back to IPv4 quickly. ``prefer_ipv4()``
patches ``socket.getaddrinfo`` (idempotently) to drop AF_INET6 results so
httpx connects over IPv4.

Call it before creating an httpx client. It is opt-in (not applied on import)
so importing ``core`` stays side-effect free.
"""
from __future__ import annotations

import socket

_installed = False


def prefer_ipv4() -> None:
    global _installed
    if _installed:
        return
    original = socket.getaddrinfo

    def ipv4_only(*args, **kwargs):
        results = original(*args, **kwargs)
        ipv4 = [r for r in results if r[0] == socket.AF_INET]
        return ipv4 or results

    socket.getaddrinfo = ipv4_only
    _installed = True
