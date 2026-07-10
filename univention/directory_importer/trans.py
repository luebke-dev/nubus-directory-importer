# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2025 Univention GmbH

"""
univention.directory_importer.trans - customer Transformer classes
"""

import logging

from junkaptor import decode_list
from junkaptor.trans import Transformer

from .sanitize import extract_domain_from_dn


class DomainBasedUsernameTransformer:
    """
    Appends the domain encoded in the source DN to the username attribute,
    e.g. CN=John.Doe,...,DC=sub,DC=example,DC=com turns username john.doe
    into john.doe_sub.example.com. Unlike the junkaptor transformers this
    one needs the source DN, which is not part of the record, so it is
    invoked separately by the Connector.
    """

    __slots__ = ("_username_attr", "_separator")

    def __init__(self, username_attr: str = "username", separator: str = "_"):
        self._username_attr = username_attr
        self._separator = separator

    def __call__(self, record, source_dn=None):
        if not source_dn:
            logging.warning(
                "No source DN provided, skipping domain-based username "
                "transformation",
            )
            return record
        domain = extract_domain_from_dn(source_dn)
        if not domain:
            logging.warning("Could not extract domain from DN: %s", source_dn)
            return record
        if self._username_attr not in record:
            return record
        username_vals = record[self._username_attr]
        if isinstance(username_vals, list):
            username_val = username_vals[0]
        else:
            username_val = username_vals
        if not isinstance(username_val, bytes):
            username_val = username_val.encode("utf-8")
        username = username_val.decode("utf-8")
        new_username = f"{username}{self._separator}{domain}"
        record[self._username_attr] = [new_username.encode("utf-8")]
        logging.debug(
            "Changed username %r to %r based on DN %r",
            username,
            new_username,
            source_dn,
        )
        return record


class MemberRefsTransformer(Transformer):
    """
    Transformer class for sanitizing group member references
    based on primary key
    """

    __slots__ = (
        "_user_primary_key",
        "_group_primary_key",
        "_users",
        "_groups",
        "_id2dn_users",
        "_id2dn_groups",
        "_user_srckey_attr",
        "_group_srckey_attr",
        "_user_sanitizer",
        "_group_sanitizer",
        "_user_trans",
        "_group_trans",
    )

    def __init__(
        self,
        user_primary_key,
        user_trans,
        users,
        id2dn_users,
        group_primary_key,
        group_trans,
        groups,
        id2dn_groups,
    ):
        self._user_primary_key = user_primary_key
        self._user_trans = user_trans
        self._users = users
        self._id2dn_users = id2dn_users
        self._user_srckey_attr = user_trans._rename_attrs[user_primary_key]
        logging.debug("_user_srckey_attr = %r", self._user_srckey_attr)
        self._user_sanitizer = user_trans._sanitizer.get(
            self._user_srckey_attr,
            [lambda x: x],
        )[0]
        logging.debug("_user_sanitizer = %r", self._user_sanitizer)
        self._group_primary_key = group_primary_key
        self._group_trans = group_trans
        self._groups = groups
        self._id2dn_groups = id2dn_groups
        self._group_srckey_attr = group_trans._rename_attrs[group_primary_key]
        logging.debug("_group_srckey_attr = %r", self._group_srckey_attr)
        self._group_sanitizer = group_trans._sanitizer.get(
            self._group_srckey_attr,
            [lambda x: x],
        )[0]
        logging.debug("_group_sanitizer = %r", self._group_sanitizer)

    def __call__(self, record):
        members = decode_list(record.get("users", []))
        record["nestedGroup"] = []
        for member in members:
            if member in self._groups:
                primary_key = None
                try:
                    source_val = self._group_sanitizer(
                        self._groups[member][self._group_srckey_attr][0],
                    )
                    primary_key = source_val.decode("utf-8")
                    record["nestedGroup"].append(
                        self._id2dn_groups[primary_key].encode("utf-8"),
                    )
                except KeyError as err:
                    logging.warning(
                        "Error mapping %s - %s: %r",
                        member,
                        primary_key,
                        err,
                    )
        record["users"] = []
        for member in members:
            if member in self._users:
                primary_key = None
                try:
                    source_val = self._user_sanitizer(
                        self._users[member][self._user_srckey_attr][0],
                    )
                    primary_key = source_val.decode("utf-8")
                    record["users"].append(
                        self._id2dn_users[primary_key].encode("utf-8"),
                    )
                except KeyError as err:
                    logging.warning(
                        "Error mapping %s - %s: %r",
                        member,
                        primary_key,
                        err,
                    )
        return record
