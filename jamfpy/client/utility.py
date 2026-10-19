"""Utility functions and helper methods for the Jamf Pro API client."""
from collections.abc import Mapping
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import cast
import xml.etree.ElementTree as ET
from xml.dom import minidom


def extract_cloud_tenant_name_from_url(fqdn: str) -> str:
    """Extracts the tenant name from a Jamf Cloud URL (e.g. 'tenant' from 'https://tenant.jamfcloud.com').
        Everything after the slashes, before the first dot of an fqdn
        This is where the unique identifier of a Jamf Pro Cloud instance is found.
    """
    return fqdn.split("//")[1].split(".")[0]


def user_agent() -> str:
    """The User-Agent jamfpy identifies itself with: ``jamfpy/<installed version>``, or ``jamfpy/unknown``."""
    try:
        return f"jamfpy/{metadata.version('jamfpy')}"
    except metadata.PackageNotFoundError:
        # Imported from a source tree that was never installed (e.g. vendored), so there is no distribution to ask.
        return "jamfpy/unknown"


def compare_dict_keys(dict1: Mapping[str, object], dict2: Mapping[str, object]) -> list[str]:
    """Returns duplicate keys from 2 supplied dictionaries"""
    dict1_keys = dict1.keys()
    dict2_keys = dict2.keys()
    matched_keys = list(set(dict1_keys) & set(dict2_keys))
    return matched_keys


def format_jamf_datetime(date_time_code: str) -> datetime:
    """Accepts Jamf style code (i.e last check in) and returns Datetime object for compatibility"""
    datetime_compatible = date_time_code.replace("T", " ").split(".")[0]
    formatted_datetime = datetime.strptime(datetime_compatible, "%Y-%m-%d %H:%M:%S")
    return formatted_datetime


def create_single_file_payload(path_to_file: Path, filename_at_endpoint: str, file_format: str) -> dict[str, tuple[str, bytes, str]]:
    """Creates a single file payload"""
    with open(path_to_file, "rb") as file:
        return {"file": (filename_at_endpoint, file.read(), f"image/{file_format}")}


def pretty_xml(xml_data: str) -> str:
    """returns pretty xml from string"""
    tree = ET.ElementTree(ET.fromstring(xml_data))
    # Built from a parsed element, so the root is never None.
    rough_string = ET.tostring(cast(ET.Element, tree.getroot()), 'utf-8')
    reparsed = minidom.parseString(rough_string)

    return reparsed.toprettyxml(indent="  ")
