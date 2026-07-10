# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2025 Univention GmbH

"""
univention.directory_importer.config - parsing configuration
"""

import re
from typing import Sequence

import certifi
import strictyaml

# from python-ldap package
from ldapurl import SEARCH_SCOPE, LDAPUrl
from strictyaml import (
    Bool,
    Enum,
    Float,
    Int,
    Map,
    MapPattern,
    Optional,
    Seq,
    Str,
)

from junkaptor.trans import Transformer

__all__ = ("ConnectorConfig",)


CFG_ENCODING = "utf-8"

CFG_USER_ATTRS_DEFAULT = [
    "objectGUID",
    "entryUUID",
    "userPrincipalName",
    "cn",
    "givenName",
    "sn",
    "mail",
    "telephoneNumber",
    "mobile",
    "memberOf",
    "proxyAddresses",
]

CFG_GRP_ATTRS_DEFAULT = [
    "objectGUID",
    "entryUUID",
    "cn",
    "member",
]

CFG_USER_PROPS_DEFAULT = [
    "city",
    "country",
    "departmentNumber",
    "description",
    "e-mail",
    "employeeNumber",
    "employeeType",
    "firstname",
    "homePostalAddress",
    "homeTelephoneNumber",
    "initials",
    "jpegPhoto",
    "lastname",
    "mailPrimaryAddress",
    "mobileTelephoneNumber",
    "organisation",
    "phone",
    "physicalDeliveryOfficeName",
    "postOfficeBox",
    "postcode",
    "preferredDeliveryMethod",
    "preferredLanguage",
    "roomNumber",
    "secretary",
    "street",
    "title",
    "username",
    "univentionObjectIdentifier",
]

CFG_GROUP_PROPS_DEFAULT = [
    "name",
    "description",
    "users",
    "nestedGroup",
    "univentionObjectIdentifier",
]

CFG_SCHEMA_UDM = Map(
    {
        "uri": Str(),
        "user": Str(),
        "password": Str(),
        Optional("ca_cert", default=certifi.where()): Str(),
        Optional("skip_writes", default=False): Bool(),
        Optional("connect_timeout", default=6.0): Float(),
        Optional("read_timeout", default=1800.0): Float(),
        "user_ou": Str(),
        Optional("user_primary_key_property", default="uniqueIdentifier"): Str(),
        Optional("user_properties", default=CFG_USER_PROPS_DEFAULT): Seq(Str()),
        "group_ou": Str(),
        Optional("group_primary_key_property", default="uniqueIdentifier"): Str(),
        Optional("group_properties", default=CFG_GROUP_PROPS_DEFAULT): Seq(Str()),
    },
)

CFG_TRANSFORMER = Map(
    {
        Optional(
            "sanitizer",
            default={
                "objectGUID": ["univention.directory_importer.sanitize:guid2uuid"],
                "telephoneNumber": [
                    "univention.directory_importer.sanitize:phone_sanitizer",
                ],
                "mobile": ["univention.directory_importer.sanitize:phone_sanitizer"],
                "mobileTelephoneNumber": [
                    "univention.directory_importer.sanitize:phone_sanitizer",
                ],
                "homePhone": ["univention.directory_importer.sanitize:phone_sanitizer"],
                "homeTelephoneNumber": [
                    "univention.directory_importer.sanitize:phone_sanitizer",
                ],
                "facsimileTelephoneNumber": [
                    "univention.directory_importer.sanitize:phone_sanitizer",
                ],
                "fax": ["univention.directory_importer.sanitize:phone_sanitizer"],
                #'mail': ['univention.directory_importer.sanitize:mail_sanitizer'],
                #'mailPrimaryAddress': ['univention.directory_importer.sanitize:mail_sanitizer'],
                #'mailLocalAddress': ['univention.directory_importer.sanitize:mail_sanitizer'],
                #'mailAlternativeAddress': ['univention.directory_importer.sanitize:mail_sanitizer'],
            },
        ): MapPattern(Str(), Seq(Str())),
        Optional("fixed_attrs"): MapPattern(Str(), Seq(Str())),
        Optional("fallback_attrs"): MapPattern(Str(), Seq(Str())),
        Optional("rename_attrs"): MapPattern(Str(), Str()),
        Optional("compose_attrs"): MapPattern(Str(), Seq(Str())),
        Optional("remove_attrs"): Seq(Str()),
        Optional("remove_values"): MapPattern(Str(), Seq(Str())),
        Optional("recode_attrs"): MapPattern(Str(), Str()),
        Optional("replace_values"): MapPattern(Str(), MapPattern(Str(), Str())),
        Optional("decompose_attrs"): MapPattern(Str(), Seq(Str())),
    },
)

CFG_SCHEMA_SOURCE_LDAP = Map(
    {
        "ldap_uri": Str(),
        Optional("bind_dn"): Str(),
        Optional("password"): Str(),
        Optional("sasl_method"): Str(),
        Optional("ca_cert", default=certifi.where()): Str(),
        Optional("timeout", default=5.0): Float(),
        Optional("trace_level", default=0): Int(),
        Optional("search_pagesize", default=500): Int(),
        Optional("ignore_dn_regex"): Str(),
        Optional("enable_domain_based_username", default=False): Bool(),
        Optional("domain_based_username_attr", default="username"): Str(),
        Optional("domain_based_username_separator", default="_"): Str(),
        "user_base": Str(),
        Optional("user_scope", default="sub"): Enum(("one", "sub")),
        Optional("user_filter", default="(objectClass=user)"): Str(),
        Optional("user_attrs", default=CFG_USER_ATTRS_DEFAULT): Seq(Str()),
        Optional("user_range_attrs", default=["memberOf"]): Seq(Str()),
        Optional("user_trans"): CFG_TRANSFORMER,
        "group_base": Str(),
        Optional("group_scope", default="sub"): Enum(("one", "sub")),
        Optional("group_filter", default="(objectClass=group)"): Str(),
        Optional("group_attrs", default=CFG_GRP_ATTRS_DEFAULT): Seq(Str()),
        Optional("group_range_attrs", default=["member"]): Seq(Str()),
        Optional("group_trans"): CFG_TRANSFORMER,
    },
)

CFG_MAPPING_RULE = Map(
    {
        "group": Str(),
        "attribute": Str(),
        "value_if_member": Str(),
        Optional("value_if_not_member"): Str(),
    },
)

CFG_GROUP_ATTRIBUTE_MAPPING = Map(
    {
        Optional("enabled", default=False): Bool(),
        "group_base": Str(),
        Optional("group_scope", default="sub"): Enum(("one", "sub")),
        Optional("group_filter", default="(objectClass=group)"): Str(),
        "mapping": Seq(CFG_MAPPING_RULE),
    },
)

CFG_SCHEMA = Map(
    {
        "udm": CFG_SCHEMA_UDM,
        "source": CFG_SCHEMA_SOURCE_LDAP,
        Optional("group_attribute_mapping"): CFG_GROUP_ATTRIBUTE_MAPPING,
    },
)


class SourceConfig:
    """
    Model for a single source connector configuration
    """

    __slots__ = (
        "_yml",
        # Connection config
        "ldap_uri",
        "bind_dn",
        "password",
        "ca_cert",
        # Logging config
        "trace_level",
        # Performance config
        "timeout",
        "search_pagesize",
        # Functional config
        "enable_domain_based_username",
        "domain_based_username_attr",
        "domain_based_username_separator",
        "user_base",
        "user_scope",
        "user_filter",
        "user_attrs",
        "user_range_attrs",
        "user_trans",
        "group_base",
        "group_scope",
        "group_filter",
        "group_attrs",
        "group_range_attrs",
        "group_trans",
    )

    ldap_uri: LDAPUrl
    bind_dn: str
    password: bytes
    ca_cert: str
    trace_level: int
    timeout: float
    search_pagesize: int
    user_base: str
    user_scope: int
    user_filter: str
    user_attrs: Sequence[str]
    user_range_attrs: Sequence[str]
    user_trans: Transformer
    group_base: str
    group_scope: int
    group_filter: str
    group_attrs: Sequence[str]
    group_range_attrs: Sequence[str]
    group_trans: Transformer

    def __init__(self, yml, password=None):
        self._yml = yml
        self.ldap_uri = LDAPUrl(yml["ldap_uri"].text)
        self.bind_dn = yml["bind_dn"].text
        self.password = (password or yml.get("password").text).encode("utf-8")
        self.ca_cert = yml["ca_cert"].text
        self.trace_level = yml["trace_level"].data
        self.timeout = yml["timeout"].data
        self.search_pagesize = yml["search_pagesize"].data
        self.enable_domain_based_username = yml[
            "enable_domain_based_username"
        ].data
        self.domain_based_username_attr = yml["domain_based_username_attr"].text
        self.domain_based_username_separator = yml[
            "domain_based_username_separator"
        ].text
        self.user_base = yml["user_base"].text
        self.user_scope = SEARCH_SCOPE[yml["user_scope"].text]
        self.user_filter = yml["user_filter"].text
        self.user_attrs = yml["user_attrs"].data
        self.user_range_attrs = yml["user_range_attrs"].data
        self.user_trans = Transformer(**self._yml["user_trans"].data)
        self.group_base = yml["group_base"].text
        self.group_scope = SEARCH_SCOPE[yml["group_scope"].text]
        self.group_filter = yml["group_filter"].text
        self.group_attrs = yml["group_attrs"].data
        self.group_range_attrs = yml["group_range_attrs"].data
        self.group_trans = Transformer(**self._yml["group_trans"].data)

    @property
    def ignore_dn_regex(self):
        val = self._yml.get("ignore_dn_regex", None)
        if val is not None:
            val = re.compile(val.text)
        return val


class UDMConfig:
    """
    UDM configuration parameter class
    """

    __slots__ = (
        "_yml",
        # Connection config
        "uri",
        "user",
        "password",
        "ca_cert",
        # debug config
        "skip_writes",
        # Performance config
        "connect_timeout",
        "read_timeout",
        # Functional config
        "user_ou",
        "user_primary_key_property",
        "user_properties",
        "group_ou",
        "group_primary_key_property",
        "group_properties",
    )

    uri: str
    user: str
    password: str
    ca_cert: str
    skip_writes: bool
    timeout: float
    user_ou: str
    group_ou: str
    user_primary_key_property: str
    group_primary_key_property: str

    def __init__(self, yml, password=None):
        self._yml = yml
        self.uri = yml["uri"].text
        self.user = yml["user"].text
        self.password = password or yml["password"].text
        self.ca_cert = yml["ca_cert"].text
        self.skip_writes = yml["skip_writes"].data
        self.connect_timeout = yml["connect_timeout"].data
        self.read_timeout = yml["read_timeout"].data
        self.user_ou = yml["user_ou"].text
        self.user_primary_key_property = yml["user_primary_key_property"].text
        self.user_properties = set(yml["user_properties"].data)
        self.group_ou = yml["group_ou"].text
        self.group_primary_key_property = yml["group_primary_key_property"].text
        self.group_properties = set(yml["group_properties"].data)


class MappingRule:
    """
    a single group membership to attribute value mapping rule
    """

    __slots__ = ("group", "attribute", "value_if_member", "value_if_not_member")

    group: str
    attribute: str
    value_if_member: str

    def __init__(self, yml):
        self.group = yml["group"].text
        self.attribute = yml["attribute"].text
        self.value_if_member = yml["value_if_member"].text
        value_if_not_member = yml.get("value_if_not_member")
        self.value_if_not_member = (
            value_if_not_member.text if value_if_not_member is not None else None
        )


class GroupAttributeMappingConfig:
    """
    configuration for mapping source group memberships to target user
    attribute values
    """

    __slots__ = ("enabled", "group_base", "group_scope", "group_filter", "mapping")

    enabled: bool
    group_base: str
    group_scope: int
    group_filter: str

    def __init__(self, yml):
        self.enabled = yml["enabled"].data
        self.group_base = yml["group_base"].text
        self.group_scope = SEARCH_SCOPE[yml["group_scope"].text]
        self.group_filter = yml["group_filter"].text
        self.mapping = [MappingRule(rule) for rule in yml["mapping"]]


class ConnectorConfig:
    """
    Model for the complete connector configuration
    """

    __slots__ = (
        "state",
        "src",
        "udm",
        "group_attribute_mapping",
    )

    src: SourceConfig
    udm: UDMConfig

    def __init__(self, config_filename, source_password=None, udm_password=None):
        with open(config_filename, "r", encoding=CFG_ENCODING) as config_file:
            yml = strictyaml.load(config_file.read(), CFG_SCHEMA)
        self.src = SourceConfig(yml["source"], password=source_password)
        self.udm = UDMConfig(yml["udm"], password=udm_password)
        mapping_yml = yml.get("group_attribute_mapping")
        self.group_attribute_mapping = (
            GroupAttributeMappingConfig(mapping_yml)
            if mapping_yml is not None
            else None
        )
