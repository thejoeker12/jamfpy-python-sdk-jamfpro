import sys, os

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpi
from pprint import pprint
import html




config = jamfpi.import_json("client_auth.json")

jamf = jamfpi.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=20,
    safe_mode=True
)

obj = jamf.classic.configuration_profiles.get_by_id(280)

wrapper = open("wrapper.xml", 'r').read()

with open("test_config_profile.mobileconfig", "r") as file:
    raw_payload = file.read()
    escaped_payload = html.escape(raw_payload)
    complete = wrapper.format(PAYLOAD=escaped_payload)
    print(complete)
    update = jamf.classic.configuration_profiles.create(complete)