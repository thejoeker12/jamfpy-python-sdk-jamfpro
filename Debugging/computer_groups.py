"""Just a template"""
import sys
import os

# pylint: disable=wrong-import-position, R0801

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

import jamfpy
from pprint import pprint
from random import randint as r
from xml.etree import ElementTree

config = jamfpy.import_json("clientauth.json")

jamf = jamfpy.init_client(
    tenant_name=config["instanceName"],
    client_id=config["clientId"],
    client_secret=config["clientSecret"]
)


def get(res_id):
    group = jamf.classic.computergroups.get_by_id(res_id)
    if group.ok:
        return group.text



def make():
    name = f"Group Creation Test {r(1, 999999)}"
    print(name)
    xml = open("computer_group.xml").read().format(NAME=name)
    create = jamf.classic.computergroups.create(xml)
    if not create.ok:
        raise Exception from create.text
    
    xml_data = create.text
    root = ElementTree.fromstring(xml_data)
    resource_id = root.find("id").text

    return resource_id, name


def delete_all_computer_groups(exclude: list):
    all_resources = jamf.classic.computergroups.get_all()

    if all_resources.ok:
        resource_json = all_resources.json()["computer_groups"]
    else:
        raise Exception("problem")
    
    for i in resource_json:
        if str(i["id"]) not in exclude:
            delete = jamf.classic.computergroups.delete_by_id(i["id"])
            if delete.ok:
                print(f"Deleted {i['id']} successfully")
            else:
                print(f"problem with {i['id']}, skipping...")


def save(fn, xml):
    with open(fn, "w", encoding="UTF-8") as f: 
        f.write(xml)


delete_all_computer_groups([])
resid, name = make()
xml = get(resid)
save(name, xml)
