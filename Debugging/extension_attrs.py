"""Just a template"""
import sys
import os

# pylint: disable=wrong-import-position, R0801

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpi

config = jamfpi.import_json("clientauth.json")

jamf = jamfpi.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
	logging_level=10
)

data = """ 
<computer_extension_attribute>
	<name>Battery Cycle Count1</name>
	<description>Number of charge cycles logged on the current battery</description>
	<data_type>integer</data_type>
</computer_extension_attribute>
"""
new_attr = jamf.classic.computer_extension_attributes.create(data)
print(new_attr)