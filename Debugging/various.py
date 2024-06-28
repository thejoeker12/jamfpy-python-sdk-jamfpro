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
from pprint import pprint

config = jamfpi.import_json("clientauth.json")

jamf = jamfpi.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"]
)




urls = [
    "https://lbgsandbox.jamfcloud.com/JSSResource/accounts/userid/510",
    "https://lbgsandbox.jamfcloud.com/JSSResource/accounts/groupid/1789"
]

for url in urls:
    request = requests.Request("GET", url=url)
    resp = jamf.classic.do(request, error_on_fail=False)
    xml = parseString(resp.text)
    print(url)
    print(xml.toprettyxml())
    print("\n\n-------------------\n\n")

