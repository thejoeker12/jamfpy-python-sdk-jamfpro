"""Unit tests for jamfpy.client.client (endpoint wiring on ClassicAPI / ProAPI).

Builds a real ``Tenant`` with the token endpoint answered by ``mocked_responses``.
"""
# pylint: disable=missing-function-docstring
import logging
from unittest.mock import patch

from conftest import FQDN, register_oauth_token

import jamfpy


def test_classic_api_builds_policies_once(mocked_responses):
    register_oauth_token(mocked_responses)
    with patch("jamfpy.client.client.Policies") as mock_policies:
        tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c", client_secret="s",
                               log_level=logging.CRITICAL)

    mock_policies.assert_called_once_with(tenant.classic)
    assert tenant.classic.policies is mock_policies.return_value
