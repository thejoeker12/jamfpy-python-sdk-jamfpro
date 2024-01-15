import sys, os

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpi
from pprint import pprint
from pathlib import Path

config = jamfpi.import_json("client_auth.json")

jamf = jamfpi.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=10,
    safe_mode=False
)

# policy_with_icon = jamf.classic.policies.get_by_id(198, "json")
# print(policy_with_icon)
# pprint(policy_with_icon.json())

# icon = jamf.pro.icons.get_by_id(2)
# print(icon)
# pprint(icon.json())

upload = jamf.pro.icons.upload(Path("cat.png"))
print(upload)