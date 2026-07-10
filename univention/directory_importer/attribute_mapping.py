# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2025 Univention GmbH

"""
univention.directory_importer.attribute_mapping - group membership based
attribute values

Resolves (nested) group memberships from the source directory and sets
target user properties based on configurable mapping rules, e.g. openDesk
service flags like opendeskFileshareEnabled.
"""

import logging
from collections import defaultdict

from junkaptor import decode_list

from .udm import UDMModel


class GroupResolver:
    """
    Resolves nested group memberships from source LDAP data with cycle
    detection.
    """

    __slots__ = ("_groups", "_cn_to_dn", "_member_to_groups", "_resolved")

    def __init__(self, source_groups: dict):
        self._groups = source_groups
        self._cn_to_dn = {}
        for dn, attrs in source_groups.items():
            cn_vals = attrs.get("cn", [])
            if cn_vals:
                cn = (
                    cn_vals[0].decode("utf-8")
                    if isinstance(cn_vals[0], bytes)
                    else cn_vals[0]
                )
                self._cn_to_dn[cn.lower()] = dn
        self._member_to_groups = defaultdict(set)
        for dn, attrs in source_groups.items():
            for member in decode_list(attrs.get("member", [])):
                self._member_to_groups[member].add(dn)
        self._resolved = {}

    def get_user_groups(self, user_dn: str) -> set:
        """
        returns all group DNs a user belongs to, including nested groups
        """
        if user_dn in self._resolved:
            return self._resolved[user_dn]
        all_groups = set()
        to_check = set(self._member_to_groups.get(user_dn, set()))
        while to_check:
            group_dn = to_check.pop()
            if group_dn in all_groups:
                continue
            all_groups.add(group_dn)
            to_check |= self._member_to_groups.get(group_dn, set()) - all_groups
        self._resolved[user_dn] = all_groups
        return all_groups

    def resolve_group(self, group_ref: str):
        """
        resolves a group reference to a DN, a reference containing '=' is
        treated as full DN, anything else as CN (both case-insensitive)
        """
        if "=" in group_ref:
            ref_lower = group_ref.lower()
            for dn in self._groups:
                if dn.lower() == ref_lower:
                    return dn
            return None
        return self._cn_to_dn.get(group_ref.lower())


def compute_mapped_attrs(
    user_dn: str,
    resolver: GroupResolver,
    mapping_rules: list,
) -> dict:
    """
    returns {udm_property: value} for a user based on the mapping rules,
    membership values always win, among value_if_not_member defaults the
    first rule wins
    """
    user_groups = resolver.get_user_groups(user_dn)
    result = {}
    for rule in mapping_rules:
        group_dn = resolver.resolve_group(rule.group)
        if group_dn is not None and group_dn in user_groups:
            result[rule.attribute] = rule.value_if_member
        elif rule.value_if_not_member is not None:
            result.setdefault(rule.attribute, rule.value_if_not_member)
    return result


def coerce_properties(attrs: dict, tmpl_props: dict) -> dict:
    """
    coerces string values from the YAML config to the property types the
    UDM REST API expects, based on the UDM template
    """
    result = {}
    for key, value in attrs.items():
        tmpl_value = tmpl_props.get(key)
        if isinstance(tmpl_value, bool):
            result[key] = value.upper() in ("TRUE", "1", "YES")
        elif isinstance(tmpl_value, list) and not isinstance(value, list):
            result[key] = [value]
        else:
            result[key] = value
    return result


def run_group_attribute_mapping(
    connector,
    config,
    source_users,
    id2dn_users,
    old_users,
):
    """
    resolve source group memberships and set the mapped user properties,
    entries whose current properties already match are skipped
    """
    mapping_config = config.group_attribute_mapping
    if mapping_config is None or not mapping_config.enabled:
        return
    if not mapping_config.mapping:
        return

    logging.info(
        "Starting group attribute mapping with %d rules",
        len(mapping_config.mapping),
    )
    mapping_groups = dict(
        connector.source_search(
            mapping_config.group_base,
            mapping_config.group_scope,
            mapping_config.group_filter,
            ["cn", "member"],
            ["member"],
        ),
    )
    logging.debug("Found %d groups for attribute mapping", len(mapping_groups))
    resolver = GroupResolver(mapping_groups)

    tmpl_props = connector._udm.get_template(UDMModel.USER)["properties"]
    dn2props = {entry.dn: entry.properties for entry in old_users.values()}

    user_trans = config.src.user_trans
    src_key_attr = user_trans._rename_attrs.get(
        config.udm.user_primary_key_property,
    )
    src_key_sanitizer = user_trans._sanitizer.get(src_key_attr, [lambda x: x])[0]

    modified_count = skipped_count = error_count = 0
    for source_dn, source_entry in source_users.items():
        src_key_vals = source_entry.get(src_key_attr)
        if not src_key_vals:
            skipped_count += 1
            continue
        try:
            primary_key = src_key_sanitizer(src_key_vals[0]).decode("utf-8")
        except Exception:
            logging.debug("Could not resolve primary key for %s", source_dn)
            skipped_count += 1
            continue
        target_dn = id2dn_users.get(primary_key)
        if not target_dn:
            skipped_count += 1
            continue

        new_attrs = compute_mapped_attrs(
            source_dn,
            resolver,
            mapping_config.mapping,
        )
        if not new_attrs:
            skipped_count += 1
            continue
        new_attrs = coerce_properties(new_attrs, tmpl_props)

        current_props = dn2props.get(target_dn)
        if current_props is not None and all(
            current_props.get(key) == value for key, value in new_attrs.items()
        ):
            skipped_count += 1
            continue

        try:
            connector._udm.modify(UDMModel.USER, target_dn, new_attrs)
        except Exception as err:
            error_count += 1
            logging.error("Attribute mapping error for %s: %s", target_dn, err)
        else:
            modified_count += 1
            logging.info(
                "Attribute mapping: set %s on %s",
                ", ".join(f"{k}={v}" for k, v in new_attrs.items()),
                target_dn,
            )

    logging.info(
        "Group attribute mapping finished: %d modified, %d skipped, %d errors",
        modified_count,
        skipped_count,
        error_count,
    )
