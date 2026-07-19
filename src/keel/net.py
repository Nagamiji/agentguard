"""Trust-aware client-IP resolution.

`X-Forwarded-For` is caller-controlled: any client can set it to an arbitrary value.
Deriving a rate-limit (or any security) identity from it without a trusted-proxy boundary
lets an attacker rotate the header to mint a fresh bucket per request and bypass the limit.

The rule enforced here:
  - The identity defaults to the **direct TCP peer** (`request.client.host`), which the
    client cannot spoof.
  - `X-Forwarded-For` is believed **only** when the peer is an explicitly configured
    trusted proxy (`KEEL_TRUSTED_PROXIES`, e.g. the Cloudflare edge / load-balancer CIDRs).
    In that case the chain is walked right-to-left, skipping further trusted hops, and the
    first untrusted address is the real client — so only hops appended by our own
    infrastructure are ever trusted.

Kept as pure functions (no Request, no Settings) so the trust logic is unit-testable in
isolation from FastAPI and Redis.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache

_UNKNOWN = "unknown"

# A parsed trusted-proxy entry: either an IPv4 or IPv6 network (a bare IP parses to a
# single-host /32 or /128). strict=False lets "10.0.0.1/8" parse as 10.0.0.0/8 rather
# than raising on set host bits.
Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=32)
def parse_trusted_proxies(csv: str) -> tuple[Network, ...]:
    """Parse a comma-separated list of IPs/CIDRs into networks; skip unparseable entries.

    A bare IP (``1.2.3.4``) becomes a /32 (or /128) single-host network. Invalid tokens
    are ignored rather than raised: a typo in ops config must not crash the request path
    (it fails safe — an unparsed proxy is simply not trusted). Cached because the config
    string is effectively constant per process.
    """
    networks: list[Network] = []
    for raw in csv.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _in_trusted(addr: str, trusted: tuple[Network, ...]) -> bool:
    """True if `addr` is a valid IP contained in any trusted network."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in trusted)


def resolve_client_ip(peer: str | None, forwarded_for: str | None, trusted_csv: str) -> str:
    """Return the client identity, trusting `X-Forwarded-For` only behind a trusted proxy.

    Args:
        peer: the direct TCP peer (`request.client.host`), or None if unknown.
        forwarded_for: the raw `X-Forwarded-For` header value, or None.
        trusted_csv: comma-separated trusted proxy IPs/CIDRs (`KEEL_TRUSTED_PROXIES`).
    """
    if not peer:
        return _UNKNOWN

    trusted = parse_trusted_proxies(trusted_csv)
    # No trusted proxy configured, or the peer is not one → the peer is the identity and any
    # X-Forwarded-For it sent is unverified and ignored. This is the anti-spoofing default.
    if not trusted or not _in_trusted(peer, trusted):
        return peer

    # Peer is a trusted proxy: walk the forwarded chain from the closest hop outward and
    # return the first address our infrastructure did not itself insert.
    hops = [h.strip() for h in (forwarded_for or "").split(",") if h.strip()]
    for hop in reversed(hops):
        if not _in_trusted(hop, trusted):
            return hop
    # Empty header, or every hop is itself a trusted proxy → fall back to the peer.
    return peer
