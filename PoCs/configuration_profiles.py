import sys, os

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpi
from pprint import pprint
from pathlib import Path
import xml.etree.ElementTree as ET
import html
import xmltodict

config = jamfpi.import_json("client_auth.json")

jamf = jamfpi.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=20,
    safe_mode=True
)

xml = jamf.classic.configuration_profiles.get_by_id(278).text
json = xmltodict.parse(xml)
plist = json["os_x_configuration_profile"]["general"]["payloads"]
plist_to_dict = xmltodict.parse(plist)

print(plist_to_dict["plist"]["dict"].keys())