"""Unit tests for the custom exception classes."""
# pylint: disable=missing-function-docstring
import pytest

from jamfpy.client.exceptions import (
    JamfAPIError,
    JamfpyConfigError,
    JamfpyInitError,
    JamfAuthError,
)

ALL_EXCEPTIONS = [JamfAPIError, JamfpyConfigError, JamfpyInitError, JamfAuthError]


@pytest.mark.parametrize("exc", ALL_EXCEPTIONS)
def test_is_exception_subclass(exc):
    assert issubclass(exc, Exception)


@pytest.mark.parametrize("exc", ALL_EXCEPTIONS)
def test_can_raise_and_catch(exc):
    with pytest.raises(exc):
        raise exc("boom")
