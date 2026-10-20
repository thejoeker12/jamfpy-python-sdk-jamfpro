"""Unit tests for jamfpy.client.utility (pure helpers)."""
# pylint: disable=missing-function-docstring
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest

from jamfpy.client.utility import (
    extract_cloud_tenant_name_from_url,
    normalise_fqdn,
    compare_dict_keys,
    format_jamf_datetime,
    create_single_file_payload,
    pretty_xml,
)


def test_extract_tenant_name_from_cloud_url():
    assert extract_cloud_tenant_name_from_url("https://acme.jamfcloud.com") == "acme"


def test_extract_tenant_name_requires_double_slash():
    with pytest.raises(IndexError):
        extract_cloud_tenant_name_from_url("acme.jamfcloud.com")


@pytest.mark.parametrize("fqdn, expected", [
    ("acme.jamfcloud.com", "https://acme.jamfcloud.com"),
    ("https://acme.jamfcloud.com", "https://acme.jamfcloud.com"),
    ("http://jamf.example.com:8080", "http://jamf.example.com:8080"),
])
def test_normalise_fqdn_adds_https_only_without_a_scheme(fqdn, expected):
    assert normalise_fqdn(fqdn) == expected


def test_compare_dict_keys_returns_intersection():
    matched = compare_dict_keys({"a": 1, "b": 2}, {"b": 3, "c": 4})
    # Order is non-deterministic (built from a set), so compare as a set.
    assert set(matched) == {"b"}


def test_compare_dict_keys_no_overlap():
    assert not compare_dict_keys({"a": 1}, {"b": 2})


def test_format_jamf_datetime_drops_fractional_and_tz():
    result = format_jamf_datetime("2024-01-01T12:00:00.000+0000")
    assert result == datetime(2024, 1, 1, 12, 0, 0)


def test_create_single_file_payload(tmp_path):
    path = tmp_path / "icon.png"
    path.write_bytes(b"\x89PNG-bytes")
    payload = create_single_file_payload(path, "icon.png", "png")
    assert payload == {"file": ("icon.png", b"\x89PNG-bytes", "image/png")}


def test_pretty_xml_formats_valid_xml():
    result = pretty_xml("<root><child>value</child></root>")
    assert result.startswith("<?xml")
    assert "<root>" in result
    assert "<child>value</child>" in result


def test_pretty_xml_rejects_invalid_xml():
    with pytest.raises(ET.ParseError):
        pretty_xml("<unclosed>")
