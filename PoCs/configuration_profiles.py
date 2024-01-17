import sys, os

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpi
from pprint import pprint




config = jamfpi.import_json("client_auth.json")

jamf = jamfpi.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=20,
    safe_mode=True
)

obj = jamf.classic.configuration_profiles.get_by_id(280)
# with open("saved.xml", "w") as file:
#     file.write(obj.text)


with open("saved.xml", "r") as file:
    updatedConfig = file.read()
    update = jamf.classic.configuration_profiles.update_by_id(280, updatedConfig)
