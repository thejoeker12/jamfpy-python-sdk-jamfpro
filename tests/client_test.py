"""Unit tests for jamfpy.client.client (endpoint wiring on ClassicAPI / ProAPI).

Construction does no network: the session is a mock and auth is never called.
"""
# pylint: disable=missing-function-docstring
from unittest.mock import MagicMock, patch

from conftest import FQDN

from jamfpy.client.client import ClassicAPI
from jamfpy.client.http_config import HTTPConfig


def test_classic_api_builds_policies_once(silent_logger):
    with patch("jamfpy.client.client.Policies") as mock_policies:
        api = ClassicAPI(fqdn=FQDN, auth=MagicMock(), http_config=HTTPConfig(),
                         session=MagicMock(), logger=silent_logger)

    mock_policies.assert_called_once_with(api)
    assert api.policies is mock_policies.return_value
