# pylint: disable=wrong-import-position, unused-import, R0801

# Dir specific setup rubbish

import sys
import os

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Script

import jamfpi
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
import requests

def new_jamf_client() -> jamfpi.JamfTenant:
    """Returns new jamf client using auth from file """
    config = jamfpi.import_json("clientauth.json")

    client = jamfpi.init_client(
        tenant_name="lbgsandbox",
        client_id=config["clientId"],
        client_secret=config["clientSecret"],
        logging_level=logging.INFO
    )

    client.classic._session.cookies.set(name="jpro-ingress", value=getCurrentIngressCookie())
    return client

POLICY_NAMES = []
def make_from_file(
        client: jamfpi.JamfTenant, 
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
        raise Exception("Error creating policy")

    xml_data = create_policy.text
    root = ElementTree.fromstring(xml_data)
    policy_id = root.find("id").text

    if save:
        get_save_json(policy_id, policy_name)
        get_save_xml(policy_id, policy_name)

    return policy_id, policy_name, create_policy


def get_save_json(jamf_id: str, client: jamfpi.JamfTenant, out_filename: str = ""):
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


def get_save_xml(jamf_id: str, client: jamfpi.JamfTenant, out_filename="PlaceholderName-"):
    """get policy by id and save to xml file"""
    out_filename += jamf_id
    get_policy = client.classic.policies.get_by_id(jamf_id, "xml")
    if not get_policy.ok:
        raise Exception("problem")
    
    policy_get_text = get_policy.text
    with open(f"{out_filename}.xml", "w", encoding="UTF-8") as out:
        out.write(policy_get_text)


def delete_all(client: jamfpi.JamfTenant):
    """Deletes all policies from jamf instance"""
    all_policies = client.classic.policies.get_all()

    if all_policies.ok:
        all_json = all_policies.json()["policies"]
    else:
        raise Exception("problem")
        
    for p in all_json:
        delete = client.classic.policies.delete_by_id(p["id"])
        if delete.ok:
            print(f"Deleted {p['id']} successfully")


def getCurrentIngressCookie():
    cookies = chrome_cookies("https://lbgsandbox.jamfcloud.com")
    if len(cookies) != 0:
        ingress_cookie = cookies["jpro-ingress"]
        return ingress_cookie
    
    raise Exception("No cookies found")


# def main():
#     client = new_jamf_client()
#     client.classic._session.cookies.set(name="jpro-ingress", value=getCurrentIngressCookie())
#     p_id, p_name = make_from_file(
#         client=client,
#         filename="policy_payload.xml",
#         save=False
#     )  

#     print(f"success creating {p_name} at {p_id}")


# def main():
#     client1 = new_jamf_client()
#     client2 = new_jamf_client()
#     client2.classic._session.cookies.set(name="jpro-ingress", value="cb9c9769c9f87d32")

#     pid1, pname1 = make_from_file(
#         client=client1,
#         filename="policy_payload.xml",
#         save=False
#     )

#     pid2, pname2 = make_from_file(
#         client=client2,
#         filename="policy_payload.xml",
#         save=False
#     )


APP1 = "cb9c9769c9f87d32"
APP2 = "f248e7b703882ffc"

def main():
    maker = new_jamf_client()
    maker.classic._session.cookies.set(
        name="jpro-ingress",
        value=APP1
    )

    checker = new_jamf_client()
    checker.classic._session.cookies.set(
        name="jpro-ingress",
        value=APP2
    )

    out_list = []
    test_count = 0
    for i in range(5):
        check_count = 0
        print(f"Starting test: {test_count}")
        target_policy_id, target_policy_name, resp = make_from_file(
            client=maker,
            filename="policy_payload.xml",
            save=False
        )
        print(resp.status_code)

        create_time = datetime.now()

        found = False
        while not found:
            print(f"Test {test_count}\nCheck Count: {check_count}")
            check = checker.classic.policies.get_by_id(target_policy_id, "xml")
            print(f"Check Status: {check.status_code}")
            if check.ok:
                found = True

            check_count += 1
            time.sleep(1)

        found_time = datetime.now()


        out = {
            "created": create_time.strftime('%Y-%m-%d %H:%M:%S'),
            "found": found_time.strftime('%Y-%m-%d %H:%M:%S'),
            "delta": found_time - create_time
        }
        print(out)
        out_list.append(out)
        test_count += 1 

    for i in out_list:
        print(i)

        







    

# def main():
#     client = new_jamf_client()
#     delete_all(client)


main()