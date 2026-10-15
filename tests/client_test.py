"""Unit tests for jamfpy.client.client (endpoint wiring on ClassicAPI / ProAPI).

Builds a real ``Tenant`` under ``mocked_responses``; construction is lazy, so no token
endpoint is registered or requested.
"""
# pylint: disable=missing-function-docstring
import logging
from unittest.mock import patch

import pytest
from conftest import FQDN

import jamfpy


@pytest.mark.usefixtures("mocked_responses")
def test_classic_api_builds_policies_once():
    with patch("jamfpy.client.client.Policies") as mock_policies:
        tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c", client_secret="s",
                               log_level=logging.CRITICAL)

    mock_policies.assert_called_once_with(tenant.classic)
    assert tenant.classic.policies is mock_policies.return_value
