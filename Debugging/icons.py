"""PoC for Icons"""

import sys
import os

# pylint: disable=wrong-import-position, unused-import, R0801

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

from pprint import pprint
from pathlib import Path
import jamfpy

config = jamfpy.import_json("/Users/joseph/github/terraform-sandbox/clientauth.json")

jamf = jamfpy.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=10,
    safe_mode=True
)

# policy_with_icon = jamf.classic.policies.get_by_id(198, "json")
# print(policy_with_icon)
# pprint(policy_with_icon.json())

# icon = jamf.pro.icons.get_by_id(2)
# print(icon)
# pprint(icon.json())

upload = jamf.pro.icons.upload(Path("/Users/joseph/github/go-api-sdk-jamfpro/examples/icon/UploadIcon/cat.png"))
print(upload)
