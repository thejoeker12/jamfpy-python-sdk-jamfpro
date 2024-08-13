# pylint: disable=wrong-import-position, unused-import, R0801

# Dir specific setup rubbish

import sys
import os

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)
sys.path.append("/Users/joseph/github/jamfpy/")

# Script

import jamfpy
import random
from xml.etree import ElementTree
import logging
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from pycookiecheat import chrome_cookies
from bs4 import BeautifulSoup
import time
from datetime import datetime
from pprint import pprint



def new_jamf_client() -> jamfpy.JamfTenant:
    """Returns new jamf client using auth from file """
    config = jamfpy.import_json("clientauth.json")

    client = jamfpy.init_client(
        tenant_name="lbgsandbox",
        client_id=config["clientId"],
        client_secret=config["clientSecret"],
        logging_level=logging.INFO
    )

    client.classic._session.cookies.set(name="jpro-ingress", value=getCurrentIngressCookie())
    return client


POLICY_NAMES = []
def make_from_file(
        client: jamfpy.JamfTenant, 
        filename: str = "policy_payload.xml", 
        save: bool = False
    ) -> tuple[str, str]:
    """Makes new policy in Jamf from file"""

    policy_name = f"Test From Python-{random.randint(1,10000)}"
    while policy_name in POLICY_NAMES:
        policy_name = f"Test From Python-{random.randint(1,10000)}"

    POLICY_NAMES.append(policy_name)

    with open(filename, "r") as file:
        policy = file.read()
        policy_with_name = policy.format(NAME=policy_name)

    create_policy = client.classic.policies.create(policy_with_name)

    if not create_policy.ok:
        print(create_policy.text)
        raise Exception("Error creating policy")

    xml_data = create_policy.text
    root = ElementTree.fromstring(xml_data)
    policy_id = root.find("id").text

    if save:
        get_save_json(policy_id, client)
        get_save_xml(policy_id, client)

    return policy_id, policy_name, create_policy


def get_save_json(jamf_id: str, client: jamfpy.JamfTenant, out_filename: str = ""):
    """get policy by id and save to json file"""
    get_policy = client.classic.policies.get_by_id(jamf_id, "json")
    if not get_policy.ok:
        raise Exception("problem")
    
    policy_get_json = get_policy.json()
    if out_filename == "":
        out_filename = policy_get_json["policy"]["general"]["name"]
    with open(f"{out_filename}.json", "w", encoding="UTF-8") as out:
        out_json = json.dumps(policy_get_json)
        out.write(out_json)


def get_save_xml(jamf_id: str, client: jamfpy.JamfTenant, out_filename="PlaceholderName-"):
    """get policy by id and save to xml file"""
    out_filename += jamf_id
    get_policy = client.classic.policies.get_by_id(jamf_id, "xml")
    if not get_policy.ok:
        raise Exception("problem")
    
    policy_get_text = get_policy.text
    with open(f"{out_filename}.xml", "w", encoding="UTF-8") as out:
        out.write(policy_get_text)

EXCLUDED = ["1029"]
def delete_all(client: jamfpy.JamfTenant):
    """Deletes all policies from jamf instance"""
    all_policies = client.classic.policies.get_all()

    if all_policies.ok:
        all_json = all_policies.json()["policies"]
    else:
        raise Exception("problem")
    
    for p in all_json:
        if str(p["id"]) not in EXCLUDED:
            delete = client.classic.policies.delete_by_id(p["id"])
            if delete.ok:
                print(f"Deleted {p['id']} successfully")


def getCurrentIngressCookie():
    cookies = chrome_cookies("https://lbgsandbox.jamfcloud.com")
    if len(cookies) != 0:
        ingress_cookie = cookies["jpro-ingress"]
        return ingress_cookie
    
    raise Exception("No cookies found")


def main(filename):
    TARGET_FILE = filename
    SAVE = True
    client = new_jamf_client()
    client.classic._session.cookies.set(name="jpro-ingress", value=getCurrentIngressCookie())
    p_id, p_name, _ = make_from_file(
        client=client,
        filename=TARGET_FILE,
        save=SAVE
    )  

    print(f"success creating {p_name} at {p_id}")

    cleanup_input = input("Cleanup?: ").lower()
    if cleanup_input in ["y", "yes"]:
        del_resp = client.classic.policies.delete_by_id(p_id)
        if del_resp.ok:
            print("deleted successfully")
    else:
        print("cleanup skipped")


def cleanup():
    client = new_jamf_client()
    delete_all(client)


def get(pid):
    client = new_jamf_client()
    get_save_xml(str(pid), client, "saved")


# main("policy_test_package.xml")
# cleanup()
get(1222)