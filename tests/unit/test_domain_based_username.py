# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2025 Univention GmbH

"""
Unit tests for domain-based username transformation
"""

import unittest

from univention.directory_importer.sanitize import extract_domain_from_dn
from univention.directory_importer.trans import DomainBasedUsernameTransformer


class TestExtractDomainFromDN(unittest.TestCase):
    """Test domain extraction from Distinguished Names"""

    def test_simple_domain(self):
        """Test simple domain extraction"""
        dn = "CN=User,DC=example,DC=com"
        self.assertEqual(extract_domain_from_dn(dn), "example.com")

    def test_complex_domain(self):
        """Test domain extraction from complex DN"""
        dn = "CN=John.Doe,OU=Desktops,OU=Office-Street-1,OU=Users,DC=sub,DC=corp,DC=example,DC=com"
        self.assertEqual(extract_domain_from_dn(dn), "sub.corp.example.com")

    def test_case_insensitive(self):
        """Test that DC extraction is case-insensitive"""
        dn = "CN=User,dc=example,Dc=com"
        self.assertEqual(extract_domain_from_dn(dn), "example.com")

    def test_no_dc_components(self):
        """Test DN without DC components returns empty string"""
        dn = "CN=User,OU=Users,O=Organization"
        self.assertEqual(extract_domain_from_dn(dn), "")

    def test_single_dc_component(self):
        """Test DN with single DC component"""
        dn = "CN=User,DC=local"
        self.assertEqual(extract_domain_from_dn(dn), "local")

    def test_escaped_characters_in_dn(self):
        """Test DN with escaped characters is handled properly"""
        dn = "CN=User\\, Special,DC=example,DC=com"
        self.assertEqual(extract_domain_from_dn(dn), "example.com")

    def test_empty_dn(self):
        """Test empty DN returns empty string"""
        self.assertEqual(extract_domain_from_dn(""), "")

    def test_malformed_dn(self):
        """Test malformed DN returns empty string gracefully"""
        self.assertEqual(extract_domain_from_dn("not-a-dn"), "")


class TestDomainBasedUsernameTransformer(unittest.TestCase):
    """Test DomainBasedUsernameTransformer"""

    def test_transform_with_source_dn(self):
        """Test record transformation with source_dn parameter"""
        transformer = DomainBasedUsernameTransformer(username_attr="username")

        record = {
            "username": [b"john.doe"],
            "firstname": [b"John"],
            "lastname": [b"Doe"],
        }

        result = transformer(
            record,
            source_dn="CN=John.Doe,OU=Users,DC=sub,DC=example,DC=com",
        )

        # Username should have domain suffix
        self.assertEqual(result["username"], [b"john.doe_sub.example.com"])

        # No internal side-channel attributes should appear
        self.assertNotIn("_dn", result)
        self.assertNotIn("_target_domain_ou", result)

        # Other attributes should remain unchanged
        self.assertEqual(result["firstname"], [b"John"])
        self.assertEqual(result["lastname"], [b"Doe"])

    def test_transform_without_source_dn(self):
        """Test record transformation without source_dn"""
        transformer = DomainBasedUsernameTransformer(username_attr="username")

        record = {
            "username": [b"john.doe"],
            "firstname": [b"John"],
        }

        result = transformer(record)

        # Username should remain unchanged
        self.assertEqual(result["username"], [b"john.doe"])

    def test_transform_with_none_source_dn(self):
        """Test with explicit None source_dn"""
        transformer = DomainBasedUsernameTransformer(username_attr="username")

        record = {"username": [b"john.doe"]}
        result = transformer(record, source_dn=None)

        self.assertEqual(result["username"], [b"john.doe"])

    def test_transform_with_string_username(self):
        """Test with username as bytes (not list)"""
        transformer = DomainBasedUsernameTransformer(username_attr="username")

        record = {"username": b"john.doe"}
        result = transformer(record, source_dn="CN=User,DC=example,DC=com")

        self.assertEqual(result["username"], [b"john.doe_example.com"])

    def test_custom_username_attr(self):
        """Test with custom username attribute"""
        transformer = DomainBasedUsernameTransformer(username_attr="uid")

        record = {"uid": [b"jdoe"]}
        result = transformer(record, source_dn="CN=User,DC=example,DC=com")

        self.assertEqual(result["uid"], [b"jdoe_example.com"])

    def test_custom_separator(self):
        """Test with custom separator"""
        transformer = DomainBasedUsernameTransformer(
            username_attr="username", separator="@"
        )

        record = {"username": [b"john.doe"]}
        result = transformer(
            record,
            source_dn="CN=John.Doe,DC=sub,DC=example,DC=com",
        )

        self.assertEqual(result["username"], [b"john.doe@sub.example.com"])

    def test_dn_without_dc_components(self):
        """Test with DN that has no DC components - username not modified"""
        transformer = DomainBasedUsernameTransformer(username_attr="username")

        record = {"username": [b"john.doe"]}
        result = transformer(record, source_dn="CN=John,OU=Users,O=Organization")

        self.assertEqual(result["username"], [b"john.doe"])

    def test_record_without_username_attr(self):
        """Test record that doesn't contain the username attribute"""
        transformer = DomainBasedUsernameTransformer(username_attr="username")

        record = {"firstname": [b"John"]}
        result = transformer(record, source_dn="CN=User,DC=example,DC=com")

        # Record should be returned unmodified
        self.assertNotIn("username", result)
        self.assertEqual(result["firstname"], [b"John"])


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# config defaults
# ---------------------------------------------------------------------------
from univention.directory_importer.config import ConnectorConfig


def test_config_defaults(connector_yaml_path):
    config = ConnectorConfig(connector_yaml_path)
    assert config.src.enable_domain_based_username is False
    assert config.src.domain_based_username_attr == "username"
    assert config.src.domain_based_username_separator == "_"
