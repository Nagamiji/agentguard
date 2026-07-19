"""Unit tests for trust-aware client-IP resolution (keel/net.py).

These pin the security property behind the provisioning rate limiter: a caller-controlled
`X-Forwarded-For` header can never set the rate-limit identity unless it arrives via an
explicitly trusted proxy. No DB / FastAPI needed — the trust logic is pure.
"""

from keel.net import parse_trusted_proxies, resolve_client_ip


class TestNoTrustedProxy:
    """Default posture: identity is the direct peer; XFF is ignored."""

    def test_spoofed_xff_is_ignored_without_trusted_proxy(self) -> None:
        # An attacker rotating X-Forwarded-For gets the same identity every time: the peer.
        assert resolve_client_ip("198.51.100.7", "1.1.1.1", "") == "198.51.100.7"
        assert resolve_client_ip("198.51.100.7", "2.2.2.2", "") == "198.51.100.7"
        assert resolve_client_ip("198.51.100.7", "evil, 3.3.3.3", "") == "198.51.100.7"

    def test_peer_not_in_trusted_set_ignores_xff(self) -> None:
        # Trusted set configured, but the peer is a random client, not the proxy → ignore XFF.
        assert resolve_client_ip("198.51.100.7", "1.1.1.1", "10.0.0.0/8") == "198.51.100.7"

    def test_missing_peer_is_unknown(self) -> None:
        assert resolve_client_ip(None, "1.1.1.1", "") == "unknown"
        assert resolve_client_ip(None, None, "10.0.0.0/8") == "unknown"


class TestBehindTrustedProxy:
    """When the peer IS a configured trusted proxy, recover the real client from XFF."""

    def test_single_trusted_proxy_returns_client(self) -> None:
        assert resolve_client_ip("10.0.0.5", "203.0.113.9", "10.0.0.5") == "203.0.113.9"

    def test_client_injected_xff_prefix_is_bypassed(self) -> None:
        # Client sends a fake left entry; the trusted proxy appends the true IP on the right.
        # Walking right-to-left, the first untrusted hop is the real client.
        got = resolve_client_ip("10.0.0.5", "evil-spoof, 203.0.113.9", "10.0.0.0/8")
        assert got == "203.0.113.9"

    def test_chained_trusted_proxies_are_skipped(self) -> None:
        # peer=proxyB(10.0.0.6); XFF = client, proxyA(10.0.0.5). Both proxies trusted →
        # skip them right-to-left and return the client.
        got = resolve_client_ip("10.0.0.6", "203.0.113.9, 10.0.0.5", "10.0.0.0/8")
        assert got == "203.0.113.9"

    def test_cidr_membership(self) -> None:
        assert resolve_client_ip("10.1.2.3", "203.0.113.9", "10.0.0.0/8") == "203.0.113.9"

    def test_malformed_left_hops_are_skipped(self) -> None:
        assert (
            resolve_client_ip("10.0.0.5", "not-an-ip, 203.0.113.9", "10.0.0.0/8") == "203.0.113.9"
        )

    def test_empty_xff_falls_back_to_peer(self) -> None:
        assert resolve_client_ip("10.0.0.5", "", "10.0.0.0/8") == "10.0.0.5"
        assert resolve_client_ip("10.0.0.5", None, "10.0.0.0/8") == "10.0.0.5"

    def test_all_hops_trusted_falls_back_to_peer(self) -> None:
        assert resolve_client_ip("10.0.0.6", "10.0.0.5, 10.0.0.4", "10.0.0.0/8") == "10.0.0.6"

    def test_ipv6_trusted_proxy(self) -> None:
        assert resolve_client_ip("2001:db8::1", "203.0.113.9", "2001:db8::/32") == "203.0.113.9"


class TestParseTrustedProxies:
    def test_mixed_ips_cidrs_and_junk(self) -> None:
        nets = parse_trusted_proxies("1.2.3.4, 10.0.0.0/8, , not-a-cidr")
        # The bare IP and the CIDR parse; blanks and junk are skipped (fail-safe, not fatal).
        assert len(nets) == 2

    def test_empty_string_is_no_proxies(self) -> None:
        assert parse_trusted_proxies("") == ()
