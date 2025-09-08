"""Utility functions and helper methods for the Jamf Pro API client."""
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom


def extract_cloud_tenant_name_from_url(fqdn: str):
    """Extracts the tenant name from a Jamf Cloud URL (e.g. 'tenant' from 'https://tenant.jamfcloud.com').
        Everything after the slashes, before the first dot of an fqdn
        This is where the unique identifier of a Jamf Pro Cloud instance is found.
    """
    return fqdn.split("//")[1].split(".")[0]


def fix_jamf_time_to_iso(time):
    """Fixes time recieved from jamf, converts to iso"""
    time.replace("Z", "+00:00")
    if len(time) in [26, 27, 28]:
        time_split = time.split(".")
        date_time_no_seconds = time_split[0]

        seconds_and_tz = time_split[1]
        s_tz_split = seconds_and_tz.split("+")

        seconds = s_tz_split[0]
        while len(seconds) < 3:
            seconds += "0"

        time = f"{date_time_no_seconds}.{seconds}+{s_tz_split[1]}"

    return time


def compare_dict_keys(dict1, dict2):
    """Returns duplicate keys from 2 supplied dictionaries"""
    dict1_keys = dict1.keys()
    dict2_keys = dict2.keys()
    matched_keys = list(set(dict1_keys) & set(dict2_keys))
    return matched_keys


def format_jamf_datetime(date_time_code):
    """Accepts Jamf style code (i.e last check in) and returns Datetime object for compatibility"""
    datetime_compatible = date_time_code.replace("T", " ").split(".")[0]
    formatted_datetime = datetime.strptime(datetime_compatible, "%Y-%m-%d %H:%M:%S")
    return formatted_datetime


def create_single_file_payload(path_to_file: Path, filename_at_endpoint: str, file_format: str):
    """Creates a single file payload"""
    with open(path_to_file, "rb") as file:
        return {"file": (filename_at_endpoint, file.read(), f"image/{file_format}")}


def pretty_xml(xml_data: str):
    """returns pretty xml from string"""
    tree = ET.ElementTree(ET.fromstring(xml_data))
    rough_string = ET.tostring(tree.getroot(), 'utf-8')
    reparsed = minidom.parseString(rough_string)

    return reparsed.toprettyxml(indent="  ")
