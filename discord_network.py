# pyright: reportPrivateUsage=false

import ssl
from typing import Any

import aiohttp


_SNI_FILTERED_DOMAINS = ("discord.com", "discord.gg", "discordapp.com", "discordapp.net")


def _normalize_dns_name(name: str) -> str:
    return name.rstrip(".").encode("idna").decode("ascii").lower()


def dns_name_matches(pattern: str, hostname: str) -> bool:
    """Match an exact DNS SAN or a wildcard covering one label."""
    try:
        normalized_pattern = _normalize_dns_name(pattern)
        normalized_hostname = _normalize_dns_name(hostname)
    except (UnicodeError, AttributeError):
        return False

    if "*" not in normalized_pattern:
        return normalized_pattern == normalized_hostname

    if normalized_pattern.count("*") != 1 or not normalized_pattern.startswith("*."):
        return False

    pattern_labels = normalized_pattern.split(".")
    hostname_labels = normalized_hostname.split(".")
    return (
        len(pattern_labels) == len(hostname_labels)
        and pattern_labels[1:] == hostname_labels[1:]
    )


def validate_certificate_hostname(certificate: dict[str, Any], hostname: str) -> None:
    """Validate a hostname against the certificate's DNS subjectAltName values."""
    dns_names = [
        str(value)
        for name_type, value in certificate.get("subjectAltName", ())
        if str(name_type).lower() == "dns"
    ]
    if any(dns_name_matches(name, hostname) for name in dns_names):
        return

    presented_names = ", ".join(dns_names) if dns_names else "no DNS names"
    raise ssl.CertificateError(
        f"hostname {hostname!r} does not match certificate SANs ({presented_names})"
    )


def should_suppress_sni(hostname: str) -> bool:
    """Return whether the network workaround should omit SNI for this host."""
    try:
        normalized_hostname = _normalize_dns_name(hostname)
    except (UnicodeError, AttributeError):
        return False

    return any(
        normalized_hostname == domain or normalized_hostname.endswith(f".{domain}")
        for domain in _SNI_FILTERED_DOMAINS
    )


class DiscordTLSConnector(aiohttp.TCPConnector):
    """An aiohttp connector that bypasses Discord-only TLS SNI filtering.

    Certificate-authority verification remains enabled. Because hostname
    checking cannot be performed by OpenSSL when SNI is omitted, every TLS
    connection is checked against its certificate SAN before aiohttp receives
    the connection.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        tls_context = ssl.create_default_context()
        tls_context.check_hostname = False
        kwargs["ssl"] = tls_context
        super().__init__(*args, **kwargs)

    async def _wrap_create_connection(
        self,
        *args: Any,
        req: aiohttp.ClientRequest,
        **kwargs: Any,
    ) -> tuple[Any, Any]:
        hostname = (
            kwargs.get("server_hostname")
            or req.server_hostname
            or req.url.raw_host
        )
        is_tls = bool(kwargs.get("ssl"))

        if is_tls and hostname and should_suppress_sni(hostname):
            # Python 3.14 requires a server_hostname when aiohttp supplies an
            # already-connected socket. An empty value satisfies asyncio while
            # omitting the TLS SNI extension.
            kwargs["server_hostname"] = ""

        transport, protocol = await super()._wrap_create_connection(
            *args,
            req=req,
            **kwargs,
        )

        if is_tls and hostname:
            try:
                ssl_object = transport.get_extra_info("ssl_object")
                if ssl_object is None:
                    raise ssl.CertificateError(
                        "TLS connection did not expose a peer certificate"
                    )
                validate_certificate_hostname(ssl_object.getpeercert(), hostname)
            except ssl.CertificateError as exc:
                transport.close()
                raise aiohttp.ClientConnectorCertificateError(
                    req.connection_key,
                    exc,
                ) from exc

        return transport, protocol
