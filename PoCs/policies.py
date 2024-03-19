"""PoC for configuration profiles"""
# pylint: disable=wrong-import-position, unused-import, R0801

import sys
import os
from pprint import pprint

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpi
import plistlib
import random
from xml.etree import ElementTree
import xml.dom.minidom
import logging
import json

config = jamfpi.import_json("clientauth.json")

client = jamfpi.init_client(
    tenant_name="lbgsandbox",
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=logging.INFO
)

def cleanup():
    all = client.classic.policies.get_all()
    if all.ok:
        all_json = all.json()["policies"]
    else:
        raise Exception("problem")\
        
    for p in all_json:
        delete = client.classic.policies.delete_by_id(p["id"])
        if delete.ok:
            print(f"Deleted {p['id']} successfully")

    print("cleanup finished")

def Make(save: bool):
    policy_name = f"Test From Python-{random.randint(1,10000)}"
    policy = open("policy_payload.xml", "r").read()
    policy_with_name = policy.format(NAME=policy_name)
    print(f"Name: {policy_name}")

    create_policy = client.classic.policies.create(policy_with_name)

    xml_data = create_policy.text
    root = ElementTree.fromstring(xml_data)
    id_number = root.find("id").text

    if save:
        GetSaveJson(id_number, policy_name)



def GetSaveJson(jamf_id, name=""):
    get_policy = client.classic.policies.get_by_id(jamf_id, "json")
    if get_policy.ok:
        policy_get_json = get_policy.json()
        if name == "":
            name = policy_get_json["policy"]["general"]["name"]
        with open(f"{name}.json", "w", encoding="UTF-8") as out:
            out_json = json.dumps(policy_get_json)
            out.write(out_json)

def GetSaveXML(jamf_id, name="PlaceholderName"):
    get_policy = client.classic.policies.get_by_id(jamf_id, "xml")
    if get_policy.ok:
        policy_get_text = get_policy.text
        with open(f"{name}.xml", "w", encoding="UTF-8") as out:
            out.write(policy_get_text)

def main():
    # Make(False)
    # GetSaveJson(292)
    GetSaveXML(310)
    # cleanup()


main()


