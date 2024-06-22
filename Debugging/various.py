"""Just a template"""
import sys
import os

# pylint: disable=wrong-import-position, R0801

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpi
import requests
from xml.dom.minidom import parseString

config = jamfpi.import_json("clientauth.json")

jamf = jamfpi.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"]
)

request = requests.Request("GET", url="https://lbgsandbox.jamfcloud.com/JSSResource/accounts/userid/505")
resp = jamf.classic.do(request, error_on_fail=False)
# print(resp.text)


xml_dom = parseString(resp.text)
pretty_xml_as_string = xml_dom.toprettyxml()
print(pretty_xml_as_string)