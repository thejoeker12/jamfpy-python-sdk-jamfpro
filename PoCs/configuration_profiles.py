"""PoC for configuration profiles"""
# pylint: disable=wrong-import-position, unused-import, R0801

import sys
import os
import xml.etree.ElementTree as ET
from pprint import pprint



this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpi
import plistlib

config = jamfpi.import_json("clientauth.json")

client = jamfpi.init_client(
    tenant_name="lbgsandbox",
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=10
)

profile = client.classic.configuration_profiles.get_by_id(325, "json")
profile_json = profile.json()
print(profile_json)