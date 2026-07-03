"""Unit tests for jamfpy.client.utility (pure helpers)."""
# pylint: disable=missing-function-docstring
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest

from jamfpy.client.utility import (
    extract_cloud_tenant_name_from_url,
    fix_jamf_time_to_iso,
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


def test_fix_jamf_time_pads_milliseconds_to_three_digits():
    # Two-digit fractional seconds get right-padded to three.
    assert fix_jamf_time_to_iso("2024-01-01T12:00:00.12+0000") == "2024-01-01T12:00:00.120+0000"


def test_fix_jamf_time_leaves_full_millisecond_string_unchanged():
    assert fix_jamf_time_to_iso("2024-01-01T12:00:00.120+0000") == "2024-01-01T12:00:00.120+0000"


def test_fix_jamf_time_replace_is_a_noop_quirk():
    # KNOWN QUIRK: line `time.replace("Z", ...)` discards its result, so a
    # trailing Z is never converted. A string whose length falls outside
    # [26, 27, 28] skips the reformat branch and returns verbatim, Z intact.
    assert fix_jamf_time_to_iso("2024-01-01T12:00:00Z") == "2024-01-01T12:00:00Z"


def test_fix_jamf_time_z_suffix_in_length_branch_raises():
    # KNOWN QUIRK: a Z-suffixed string that DOES hit the reformat branch has no
    # "+" to split on, so indexing s_tz_split[1] raises IndexError.
    with pytest.raises(IndexError):
        fix_jamf_time_to_iso("2024-01-01T12:00:00.000000Z")


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
