import ssl
import unittest

from discord_network import (
    dns_name_matches,
    should_suppress_sni,
    validate_certificate_hostname,
)


class CertificateHostnameTests(unittest.TestCase):
    def test_exact_dns_san_matches(self):
        certificate = {"subjectAltName": (("DNS", "discord.com"),)}

        validate_certificate_hostname(certificate, "discord.com")

    def test_single_level_wildcard_matches(self):
        certificate = {"subjectAltName": (("DNS", "*.discord.gg"),)}

        validate_certificate_hostname(certificate, "gateway.discord.gg")

    def test_wildcard_does_not_match_multiple_levels(self):
        self.assertFalse(dns_name_matches("*.discord.gg", "a.b.discord.gg"))

    def test_unrelated_certificate_is_rejected(self):
        certificate = {"subjectAltName": (("DNS", "example.com"),)}

        with self.assertRaises(ssl.CertificateError):
            validate_certificate_hostname(certificate, "discord.com")

    def test_certificate_without_dns_sans_is_rejected(self):
        certificate = {"subjectAltName": (("IP Address", "162.159.128.233"),)}

        with self.assertRaises(ssl.CertificateError):
            validate_certificate_hostname(certificate, "gateway.discord.gg")


class DiscordSniTests(unittest.TestCase):
    def test_sni_is_suppressed_only_for_discord_domains(self):
        suppressed = (
            "discord.com",
            "api.discord.com",
            "discord.gg",
            "gateway.discord.gg",
        )
        retained = (
            "discordapp.com",
            "cdn.discordapp.com",
            "discord.com.example.org",
            "notdiscord.gg",
            "example.com",
        )

        for hostname in suppressed:
            with self.subTest(hostname=hostname):
                self.assertTrue(should_suppress_sni(hostname))

        for hostname in retained:
            with self.subTest(hostname=hostname):
                self.assertFalse(should_suppress_sni(hostname))


if __name__ == "__main__":
    unittest.main()
