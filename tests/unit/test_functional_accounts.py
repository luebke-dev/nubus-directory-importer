# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2025 Univention GmbH

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from univention.directory_importer.config import ConnectorConfig
from univention.directory_importer.connector import (
    DEPROVISION_TS_FORMAT,
    Connector,
)
from univention.directory_importer.udm import UDMEntry, UDMModel

PRIMARY_KEY = "127adf44-3480-4cb0-bc48-a1010f657eb3"
DN = "cn=fm-info,ou=test,dc=example,dc=test"


@pytest.fixture()
def make_connector(connector_yaml_path):
    def _make(grace_days=0, fa_base=None):
        config = ConnectorConfig(connector_yaml_path)
        config.udm.deletion_grace_period_days = grace_days
        config.src.functional_account_base = fa_base
        connector = Connector.__new__(Connector)
        connector._config = config
        connector._udm = mock.Mock()
        return connector

    return _make


def _entry(properties=None):
    return UDMEntry(
        source_primary_key=PRIMARY_KEY,
        dn=DN,
        properties=properties or {},
    )


def test_config_defaults(connector_yaml_path):
    config = ConnectorConfig(connector_yaml_path)
    assert config.src.functional_account_base is None
    assert config.src.functional_account_filter == "(&(objectClass=group)(mail=*))"
    assert config.src.functional_account_trans is None
    assert (
        config.udm.functional_account_primary_key_property
        == "univentionObjectIdentifier"
    )
    assert config.udm.functional_account_ou == config.udm.user_ou
    assert "users" in config.udm.functional_account_properties


def test_sync_requires_trans(make_connector):
    connector = make_connector(fa_base="CN=Users,DC=example,DC=test")
    with pytest.raises(ValueError):
        connector.sync_functional_accounts({}, {})


def test_delete_without_grace_period(make_connector):
    connector = make_connector(grace_days=0)
    ctr = connector.delete_old_entries(
        UDMModel.FUNCTIONAL_ACCOUNT,
        {PRIMARY_KEY: _entry()},
        {},
    )
    assert ctr == 1
    connector._udm.delete.assert_called_once_with(UDMModel.FUNCTIONAL_ACCOUNT, DN)
    connector._udm.modify.assert_not_called()


def test_grace_period_deprovisions_by_revoking_users(make_connector):
    connector = make_connector(grace_days=30)
    entry = _entry({"users": ["uid=user1,ou=test,dc=example,dc=test"]})
    ctr = connector.delete_old_entries(
        UDMModel.FUNCTIONAL_ACCOUNT,
        {PRIMARY_KEY: entry},
        {},
    )
    assert ctr == 0
    connector._udm.delete.assert_not_called()
    args = connector._udm.modify.call_args
    assert args.args[0] == UDMModel.FUNCTIONAL_ACCOUNT
    assert args.args[1] == DN
    assert args.args[2]["users"] == []
    assert "disabled" not in args.args[2]
    assert "directoryImporterDeprovisionedAt" in args.args[2]


def test_grace_period_expired_deletes(make_connector):
    connector = make_connector(grace_days=30)
    ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime(
        DEPROVISION_TS_FORMAT,
    )
    entry = _entry({"directoryImporterDeprovisionedAt": ts, "users": []})
    ctr = connector.delete_old_entries(
        UDMModel.FUNCTIONAL_ACCOUNT,
        {PRIMARY_KEY: entry},
        {},
    )
    assert ctr == 1
    connector._udm.delete.assert_called_once_with(UDMModel.FUNCTIONAL_ACCOUNT, DN)


def test_grace_period_not_expired(make_connector):
    connector = make_connector(grace_days=30)
    ts = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
        DEPROVISION_TS_FORMAT,
    )
    entry = _entry({"directoryImporterDeprovisionedAt": ts, "users": []})
    ctr = connector.delete_old_entries(
        UDMModel.FUNCTIONAL_ACCOUNT,
        {PRIMARY_KEY: entry},
        {},
    )
    assert ctr == 0
    connector._udm.delete.assert_not_called()
    connector._udm.modify.assert_not_called()


def test_groups_still_deleted_immediately(make_connector):
    connector = make_connector(grace_days=30)
    ctr = connector.delete_old_entries(UDMModel.GROUP, {PRIMARY_KEY: _entry()}, {})
    assert ctr == 1
    connector._udm.delete.assert_called_once_with(UDMModel.GROUP, DN)
    connector._udm.modify.assert_not_called()
