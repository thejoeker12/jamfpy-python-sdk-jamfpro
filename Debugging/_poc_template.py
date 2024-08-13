"""Just a template"""
import sys
import os

# pylint: disable=wrong-import-position, R0801

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpy

config = jamfpy.import_json("client_auth.json")

jamf = jamfpy.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"]
)
