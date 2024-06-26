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


request = requests.Request("GET", url="https://lbgsandbox.jamfcloud.com/JSSResource/computerextensionattributes/id/5290")
resp = jamf.classic.do(request, error_on_fail=False)
print(resp.text)
xml = parseString(resp.text)
print(xml.toprettyxml())

# request = requests.Request("GET", url="https://lbgsandbox.jamfcloud.com/api/v1/scripts")
# resp = jamf.classic.do(request, error_on_fail=False)
# if resp.ok:
#     rjson = resp.json()["results"]
#     for i in rjson:
#         request = requests.Request("DELETE", url=f"https://lbgsandbox.jamfcloud.com/api/v1/scripts/{i['id']}")
#         resp = jamf.classic.do(request, error_on_fail=False)


# data = {
#     "name": "script name",
#     # "categoryId": 5
# }

# request = requests.Request("POST", url="https://lbgsandbox.jamfcloud.com/api/v1/scripts", json=data)
# resp = jamf.classic.do(request, error_on_fail=False)
# if resp.ok:
#     pprint(resp.json())
#     rjson = resp.json()
# else:
#     print("error")


# request = requests.Request("GET", url=f"https://lbgsandbox.jamfcloud.com/api/v1/scripts/{rjson['id']}")
# resp = jamf.classic.do(request, error_on_fail=False)
# if resp.ok:
#     pprint(resp.json())
# else:
#     print("error")