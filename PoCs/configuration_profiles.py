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
    logging_level=10,
    safe_mode=True
)

wrapper_template = open("wrapper.xml", 'r').read()
payload = open("Test from iMazing JL.mobileconfig", "r").read()
payload_escaped = html.escape(payload)
completed_payload = wrapper_template.format(PAYLOAD=payload_escaped, NAME="Test from iMazing JL")
with open("completed_payload_no_jamf.mobileconfig", "w") as file:
    file.write(completed_payload)

# create = jamf.classic.configuration_profiles.update_by_id(285, completed_payload)
# print(create, create.text)

get = jamf.classic.configuration_profiles.get_by_id(285)
with open("downloaded285.mobileconfig", "w") as file:
    file.write(get.text)

# print(completed_payload)