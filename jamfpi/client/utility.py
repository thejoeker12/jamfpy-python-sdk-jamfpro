"""Util"""
# pylint: disable=line-too-long, relative-beyond-top-level
# // TODO tidy this whole file up
import json
from datetime import datetime
from ..config.defaultconfig import defaultconfig
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests

def import_json(filepath) -> str:
    """imports config file and parses as json"""
    with open(filepath, "r", encoding="UTF-8") as file:
        json_file = json.load(file)

    return json_file


def get_bearer_token(basic_credentials, cloud_tenant_name) -> dict:
    """Accepts basic credentials and jamf instance strings, returns barer token"""
    config = defaultconfig
    endpoint = config["urls"]["bearer_token"]
    token_url = config["urls"]["base"].format(tenant=cloud_tenant_name) + endpoint
    headers = {"Authorization": f"Basic {basic_credentials}"}
    token_request = requests.post(token_url, headers=headers, timeout=10)
    if token_request.ok:
        return token_request.json()

    raise requests.HTTPError(f"Bad response: {token_request.status_code}\n{token_request.text}")


def generate_client_token(cloud_tenant_name, client_id, client_secret) -> dict:
    """Generated client token with secret and client id"""
    url = f"https://{cloud_tenant_name}.jamfcloud.com/api/oauth/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "client_id": client_id,
        "grant_type": "client_credentials",
        "client_secret": client_secret
    }
    call = requests.post(url=url, headers=headers, data=data, timeout=10)
    if call.ok:
        return call.json()

    raise requests.HTTPError("Bad call", call, call.text)


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
    else:
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
