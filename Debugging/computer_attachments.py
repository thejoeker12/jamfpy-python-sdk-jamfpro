"""PoC for computer Attachments"""
import sys
import os

# pylint: disable=wrong-import-position, R0801



this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

# from pprint import pprint
from pathlib import Path
import jamfpy


config = jamfpy.import_json("client_auth.json")

jamf = jamfpy.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=10,
    safe_mode=True
)

upload_to_comp = jamf.pro.computers_inventory.upload_attachment(15, Path("things.pdf"))
print(upload_to_comp)
