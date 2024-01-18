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
    safe_mode=False
)

wrapper_template = open("wrapper.xml", 'r').read()
payload = open("test_config_profile.mobileconfig", "r").read()
payload_escaped = html.escape(payload)
completed_payload = wrapper_template.format(PAYLOAD=payload_escaped)

create = jamf.classic.configuration_profiles.create(completed_payload)
