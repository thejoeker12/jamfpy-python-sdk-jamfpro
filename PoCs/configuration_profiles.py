import sys, os

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpi
from pprint import pprint
import html
import xml.etree.ElementTree as ET



config = jamfpi.import_json("client_auth.json")

jamf = jamfpi.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=10,
    safe_mode=True
)

# Make full payload
wrapper_template = open("osx_config_profile_wrapper.xml", 'r').read()
payload = open("payload.mobileconfig", "r").read()
payload_escaped = html.escape(payload)
completed_jamf_object = wrapper_template.format(PAYLOAD=payload_escaped, NAME="Test from iMazing JL Friday 19")

# Save locally before sending to Jamf
# with open("completed_jamf_object.xml", "w") as file:
#     file.write(completed_jamf_object)

# Put the profile into Jamf
# create = jamf.classic.configuration_profiles.create(completed_jamf_object)

# Re-downlaod the profile from Jamf and save it
# get = jamf.classic.configuration_profiles.get_by_id(287)
# with open("downloaded_complete_jamf_object.xml", "w") as file:
#     file.write(get.text)

# Rip the payload out of the newly saved one and save an unescaped version
with open("downloaded_complete_jamf_object.xml", "r") as file:
    downloaded_complete_jamf_object = file.read()
    root = ET.fromstring(downloaded_complete_jamf_object)
    payloads = root.find(".//payloads")
    payloads_text = payloads.text
    with open("downloaded_payload.mobileconfig", "w") as file:
        file.write(payloads_text)




