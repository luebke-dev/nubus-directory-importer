# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2025 Univention GmbH

"""
Tests for univention.directory_importer.attribute_mapping
"""

import pytest

from univention.directory_importer.attribute_mapping import GroupResolver, compute_mapped_attrs


# ---------------------------------------------------------------------------
# Helper to build mock config objects
# ---------------------------------------------------------------------------
class MockMappingRule:
    def __init__(self, group, attribute, value_if_member, value_if_not_member=None):
        self.group = group
        self.attribute = attribute
        self.value_if_member = value_if_member
        self.value_if_not_member = value_if_not_member


# ---------------------------------------------------------------------------
# Source LDAP test data
# ---------------------------------------------------------------------------
def _make_source_groups():
    """
    Group hierarchy:
        All-Users
          +-- Dept-IT
          |     +-- Team-Dev
          +-- Dept-HR

    Members:
        alice  -> Team-Dev (nested in Dept-IT -> All-Users)
        bob    -> Dept-HR (nested in All-Users)
        carol  -> All-Users (direct)
        dave   -> (no group)
    """
    return {
        "CN=All-Users,OU=Groups,DC=example,DC=com": {
            "cn": [b"All-Users"],
            "member": [
                b"CN=Dept-IT,OU=Groups,DC=example,DC=com",
                b"CN=Dept-HR,OU=Groups,DC=example,DC=com",
                b"CN=carol,OU=Users,DC=example,DC=com",
            ],
        },
        "CN=Dept-IT,OU=Groups,DC=example,DC=com": {
            "cn": [b"Dept-IT"],
            "member": [
                b"CN=Team-Dev,OU=Groups,DC=example,DC=com",
            ],
        },
        "CN=Team-Dev,OU=Groups,DC=example,DC=com": {
            "cn": [b"Team-Dev"],
            "member": [
                b"CN=alice,OU=Users,DC=example,DC=com",
            ],
        },
        "CN=Dept-HR,OU=Groups,DC=example,DC=com": {
            "cn": [b"Dept-HR"],
            "member": [
                b"CN=bob,OU=Users,DC=example,DC=com",
            ],
        },
    }


@pytest.fixture
def resolver():
    return GroupResolver(_make_source_groups())


# ---------------------------------------------------------------------------
# GroupResolver tests
# ---------------------------------------------------------------------------
class TestGroupResolver:
    def test_direct_membership(self, resolver):
        """Alice is a direct member of Team-Dev."""
        groups = resolver.get_user_groups("CN=alice,OU=Users,DC=example,DC=com")
        assert "CN=Team-Dev,OU=Groups,DC=example,DC=com" in groups

    def test_nested_membership(self, resolver):
        """Alice is in Team-Dev, which is nested in Dept-IT and then All-Users."""
        groups = resolver.get_user_groups("CN=alice,OU=Users,DC=example,DC=com")
        assert "CN=Dept-IT,OU=Groups,DC=example,DC=com" in groups
        assert "CN=All-Users,OU=Groups,DC=example,DC=com" in groups

    def test_single_level_nesting(self, resolver):
        """Bob is in Dept-HR, which is nested in All-Users."""
        groups = resolver.get_user_groups("CN=bob,OU=Users,DC=example,DC=com")
        assert "CN=Dept-HR,OU=Groups,DC=example,DC=com" in groups
        assert "CN=All-Users,OU=Groups,DC=example,DC=com" in groups
        # Bob should NOT be in Dept-IT or Team-Dev
        assert "CN=Dept-IT,OU=Groups,DC=example,DC=com" not in groups
        assert "CN=Team-Dev,OU=Groups,DC=example,DC=com" not in groups

    def test_direct_top_level_membership(self, resolver):
        """Carol is a direct member of All-Users only."""
        groups = resolver.get_user_groups("CN=carol,OU=Users,DC=example,DC=com")
        assert groups == {"CN=All-Users,OU=Groups,DC=example,DC=com"}

    def test_no_membership(self, resolver):
        """Dave is not in any group."""
        groups = resolver.get_user_groups("CN=dave,OU=Users,DC=example,DC=com")
        assert groups == set()

    def test_caching(self, resolver):
        """Second call returns cached result."""
        groups1 = resolver.get_user_groups("CN=alice,OU=Users,DC=example,DC=com")
        groups2 = resolver.get_user_groups("CN=alice,OU=Users,DC=example,DC=com")
        assert groups1 is groups2

    def test_get_group_dn_by_name(self, resolver):
        assert resolver.resolve_group("Team-Dev") == "CN=Team-Dev,OU=Groups,DC=example,DC=com"

    def test_get_group_dn_by_name_case_insensitive(self, resolver):
        assert resolver.resolve_group("TEAM-DEV") == "CN=Team-Dev,OU=Groups,DC=example,DC=com"
        assert resolver.resolve_group("team-dev") == "CN=Team-Dev,OU=Groups,DC=example,DC=com"

    def test_get_group_dn_by_name_not_found(self, resolver):
        assert resolver.resolve_group("NonExistent") is None

    def test_resolve_group_by_cn(self, resolver):
        assert resolver.resolve_group("Team-Dev") == "CN=Team-Dev,OU=Groups,DC=example,DC=com"

    def test_resolve_group_by_full_dn(self, resolver):
        assert resolver.resolve_group("CN=Team-Dev,OU=Groups,DC=example,DC=com") == "CN=Team-Dev,OU=Groups,DC=example,DC=com"

    def test_resolve_group_by_full_dn_case_insensitive(self, resolver):
        assert resolver.resolve_group("cn=team-dev,ou=groups,dc=example,dc=com") == "CN=Team-Dev,OU=Groups,DC=example,DC=com"

    def test_resolve_group_by_full_dn_not_found(self, resolver):
        assert resolver.resolve_group("CN=Team-Dev,OU=OtherOU,DC=example,DC=com") is None

    def test_resolve_group_by_full_dn_prevents_spoofing(self, resolver):
        """A group with the same CN but different OU should NOT match."""
        assert resolver.resolve_group("CN=Team-Dev,OU=Attackers,DC=evil,DC=com") is None

    def test_circular_groups(self):
        """Circular group nesting should not cause infinite loop."""
        circular_groups = {
            "CN=GroupA,DC=test": {
                "cn": [b"GroupA"],
                "member": [b"CN=GroupB,DC=test", b"CN=user1,DC=test"],
            },
            "CN=GroupB,DC=test": {
                "cn": [b"GroupB"],
                "member": [b"CN=GroupA,DC=test"],  # circular!
            },
        }
        resolver = GroupResolver(circular_groups)
        groups = resolver.get_user_groups("CN=user1,DC=test")
        assert "CN=GroupA,DC=test" in groups
        assert "CN=GroupB,DC=test" in groups

    def test_empty_groups(self):
        """Groups with no members."""
        empty_groups = {
            "CN=EmptyGroup,DC=test": {
                "cn": [b"EmptyGroup"],
                "member": [],
            },
        }
        resolver = GroupResolver(empty_groups)
        assert resolver.get_user_groups("CN=user1,DC=test") == set()


# ---------------------------------------------------------------------------
# compute_mapped_attrs tests
# ---------------------------------------------------------------------------
class TestComputeMappedAttrs:
    def test_member_gets_value(self, resolver):
        rules = [
            MockMappingRule("All-Users", "opendeskFileshareEnabled", "TRUE", "FALSE"),
        ]
        attrs = compute_mapped_attrs("CN=alice,OU=Users,DC=example,DC=com", resolver, rules)
        assert attrs == {"opendeskFileshareEnabled": "TRUE"}

    def test_non_member_gets_not_member_value(self, resolver):
        rules = [
            MockMappingRule("Team-Dev", "opendeskFileshareEnabled", "TRUE", "FALSE"),
        ]
        # Bob is NOT in Team-Dev
        attrs = compute_mapped_attrs("CN=bob,OU=Users,DC=example,DC=com", resolver, rules)
        assert attrs == {"opendeskFileshareEnabled": "FALSE"}

    def test_non_member_no_value_if_not_member(self, resolver):
        """When value_if_not_member is None, attribute is not set for non-members."""
        rules = [
            MockMappingRule("Team-Dev", "isOxUser", "OK", None),
        ]
        attrs = compute_mapped_attrs("CN=bob,OU=Users,DC=example,DC=com", resolver, rules)
        assert attrs == {}

    def test_nested_membership_triggers_rule(self, resolver):
        """Alice is in Team-Dev -> Dept-IT -> All-Users, so All-Users rule should match."""
        rules = [
            MockMappingRule("All-Users", "opendeskFileshareEnabled", "TRUE", "FALSE"),
        ]
        attrs = compute_mapped_attrs("CN=alice,OU=Users,DC=example,DC=com", resolver, rules)
        assert attrs["opendeskFileshareEnabled"] == "TRUE"

    def test_multiple_rules(self, resolver):
        rules = [
            MockMappingRule("All-Users", "opendeskFileshareEnabled", "TRUE", "FALSE"),
            MockMappingRule("Team-Dev", "opendeskProjectmanagementEnabled", "TRUE", "FALSE"),
            MockMappingRule("Dept-HR", "isOxUser", "OK"),
        ]
        # Alice: in All-Users (nested), Team-Dev (direct), NOT in Dept-HR
        attrs = compute_mapped_attrs("CN=alice,OU=Users,DC=example,DC=com", resolver, rules)
        assert attrs == {
            "opendeskFileshareEnabled": "TRUE",
            "opendeskProjectmanagementEnabled": "TRUE",
        }

    def test_nonexistent_group_in_rule(self, resolver):
        """Rule referencing a group that doesn't exist in source data."""
        rules = [
            MockMappingRule("NonExistentGroup", "opendeskFileshareEnabled", "TRUE", "FALSE"),
        ]
        attrs = compute_mapped_attrs("CN=alice,OU=Users,DC=example,DC=com", resolver, rules)
        # Non-existent group -> user is not a member -> value_if_not_member
        assert attrs == {"opendeskFileshareEnabled": "FALSE"}

    def test_first_member_rule_wins_over_not_member_default(self, resolver):
        """If a member rule sets the attr first, a later not-member default doesn't overwrite."""
        rules = [
            MockMappingRule("All-Users", "opendeskFileshareEnabled", "TRUE"),
            MockMappingRule("NonExistent", "opendeskFileshareEnabled", "TRUE", "FALSE"),
        ]
        # Alice is in All-Users -> attr set to TRUE by first rule
        # Second rule: not member of NonExistent, but setdefault won't overwrite
        attrs = compute_mapped_attrs("CN=alice,OU=Users,DC=example,DC=com", resolver, rules)
        assert attrs["opendeskFileshareEnabled"] == "TRUE"

    def test_no_rules(self, resolver):
        attrs = compute_mapped_attrs("CN=alice,OU=Users,DC=example,DC=com", resolver, [])
        assert attrs == {}

    def test_user_not_in_any_group(self, resolver):
        rules = [
            MockMappingRule("Team-Dev", "opendeskFileshareEnabled", "TRUE", "FALSE"),
        ]
        attrs = compute_mapped_attrs("CN=dave,OU=Users,DC=example,DC=com", resolver, rules)
        assert attrs == {"opendeskFileshareEnabled": "FALSE"}

    def test_rule_with_full_dn(self, resolver):
        """Mapping rule using full DN instead of CN."""
        rules = [
            MockMappingRule("CN=Team-Dev,OU=Groups,DC=example,DC=com", "isOxUser", "OK"),
        ]
        attrs = compute_mapped_attrs("CN=alice,OU=Users,DC=example,DC=com", resolver, rules)
        assert attrs == {"isOxUser": "OK"}

    def test_rule_with_full_dn_wrong_ou(self, resolver):
        """Full DN pointing to wrong OU should not match any group."""
        rules = [
            MockMappingRule("CN=Team-Dev,OU=WrongOU,DC=example,DC=com", "isOxUser", "OK", "NOPE"),
        ]
        attrs = compute_mapped_attrs("CN=alice,OU=Users,DC=example,DC=com", resolver, rules)
        assert attrs == {"isOxUser": "NOPE"}


# ---------------------------------------------------------------------------
# run_group_attribute_mapping tests (change detection)
# ---------------------------------------------------------------------------
from unittest import mock

from univention.directory_importer.attribute_mapping import (
    run_group_attribute_mapping,
)
from univention.directory_importer.config import ConnectorConfig
from univention.directory_importer.connector import Connector
from univention.directory_importer.udm import UDMEntry

USER_SOURCE_DN = "CN=alice,OU=Users,DC=example,DC=com"
USER_TARGET_DN = "uid=alice,ou=test,dc=example,dc=test"
USER_GUID = b"\x01" * 16


def _run(connector_yaml_path, current_props):
    config = ConnectorConfig(connector_yaml_path)
    config.group_attribute_mapping = mock.Mock(
        enabled=True,
        group_base="OU=Groups,DC=example,DC=com",
        group_scope=2,
        group_filter="(objectClass=group)",
        mapping=[
            MockMappingRule("All-Users", "opendeskFileshareEnabled", "TRUE", "FALSE"),
        ],
    )
    connector = Connector.__new__(Connector)
    connector._config = config
    connector._udm = mock.Mock()
    connector._udm.get_template.return_value = {
        "properties": {"opendeskFileshareEnabled": False},
    }
    src_key_attr = config.src.user_trans._rename_attrs[
        config.udm.user_primary_key_property
    ]
    source_users = {USER_SOURCE_DN: {src_key_attr: [USER_GUID]}}
    sanitizer = config.src.user_trans._sanitizer.get(
        src_key_attr,
        [lambda x: x],
    )[0]
    primary_key = sanitizer(USER_GUID).decode("utf-8")
    id2dn_users = {primary_key: USER_TARGET_DN}
    old_users = {
        primary_key: UDMEntry(
            source_primary_key=primary_key,
            dn=USER_TARGET_DN,
            properties=current_props,
        ),
    }
    with mock.patch.object(
        Connector,
        "source_search",
        return_value=iter(_make_source_groups().items()),
    ):
        run_group_attribute_mapping(
            connector,
            config,
            source_users,
            id2dn_users,
            old_users,
        )
    return connector._udm


class TestRunGroupAttributeMapping:
    def test_modifies_when_value_differs(self, connector_yaml_path):
        udm = _run(connector_yaml_path, {"opendeskFileshareEnabled": False})
        udm.modify.assert_called_once()
        assert udm.modify.call_args.args[2] == {"opendeskFileshareEnabled": True}

    def test_skips_when_value_matches(self, connector_yaml_path):
        udm = _run(connector_yaml_path, {"opendeskFileshareEnabled": True})
        udm.modify.assert_not_called()

    def test_disabled_config_is_noop(self, connector_yaml_path):
        config = ConnectorConfig(connector_yaml_path)
        assert config.group_attribute_mapping is None
        connector = Connector.__new__(Connector)
        connector._config = config
        connector._udm = mock.Mock()
        run_group_attribute_mapping(connector, config, {}, {}, {})
        connector._udm.modify.assert_not_called()
