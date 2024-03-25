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
import random
from xml.etree import ElementTree
import logging
import json
from selenium import webdriver
from pycookiecheat import chrome_cookies
from bs4 import BeautifulSoup
import time

def new_jamf_client() -> jamfpi.JamfTenant:

    config = jamfpi.import_json("clientauth.json")

    client = jamfpi.init_client(
        tenant_name="lbgsandbox",
        client_id=config["clientId"],
        client_secret=config["clientSecret"],
        logging_level=logging.INFO
    )

    return client


def delete_all():
    client = new_jamf_client()
    all_policies = client.classic.policies.get_all()
    if all_policies.ok:
        all_json = all.json()["policies"]
    else:
        raise Exception("problem")\
        
    for p in all_json:
        delete = client.classic.policies.delete_by_id(p["id"])
        if delete.ok:
            print(f"Deleted {p['id']} successfully")

    print("cleanup finished")


def make_from_file(save: bool, client: jamfpi.JamfTenant, payload_filename: str):
    policy_name = f"Test From Python-{random.randint(1,10000)}"
    file = open(payload_filename, "r")
    policy = file.read()
    policy_with_name = policy.format(NAME=policy_name)
    file.close()

    create_policy = client.classic.policies.create(policy_with_name)
    if not create_policy.ok:
        raise Exception("Error creating policy")


    xml_data = create_policy.text
    root = ElementTree.fromstring(xml_data)
    id_number = root.find("id").text

    if save:
        get_save_json(id_number, policy_name)
        get_save_xml(id_number, policy_name)

    return id_number


def get_save_json(jamf_id, client: jamfpi.JamfTenant, name="",):
    get_policy = client.classic.policies.get_by_id(jamf_id, "json")
    if get_policy.ok:
        policy_get_json = get_policy.json()
        if name == "":
            name = policy_get_json["policy"]["general"]["name"]
        with open(f"{name}.json", "w", encoding="UTF-8") as out:
            out_json = json.dumps(policy_get_json)
            out.write(out_json)


def get_save_xml(jamf_id, client: jamfpi.JamfTenant, name="PlaceholderName"):
    get_policy = client.classic.policies.get_by_id(jamf_id, "xml")
    if get_policy.ok:
        policy_get_text = get_policy.text
        with open(f"{name}.xml", "w", encoding="UTF-8") as out:
            out.write(policy_get_text)


# Automated GUI checking

def new_driver(init_url: str) -> dict:
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)

    driver = webdriver.Chrome(options=options)
    driver.get(init_url)


    input("Log in and then press enter...")

    return driver


def get_policy_page_source(policy_jamf_id, driver: webdriver.Chrome, wait_time: int = 5):
    driver.get(f"https://lbgsandbox.jamfcloud.com/policies.html?id={policy_jamf_id}&o=r")
    time.sleep(wait_time)
    return driver.page_source


def close_driver_with_input(driver: webdriver.Chrome):
    input("Press enter to close driver: ")
    driver.close()


def get_policy_page_status(html_text) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    print(soup.text)
    with open("out.html", "w") as file:
        file.write(str(soup))

    if 'class="code">404</h1>' in str(soup):
        return("This page was not found!: ")

    return "this page was found!: "


def single_timed_policy_propogation_test(jamf_client: jamfpi.JamfTenant, driver: webdriver.Chrome, policy_payload_filename):
    # Start timing here
    created_policy_id = make_from_file(
        save=False,
        client=jamf_client,
        payload_filename=policy_payload_filename
    )

    found = False
    while not found:
        policy_html = get_policy_page_source(created_policy_id, driver)
        found = get_policy_page_status(policy_html)

    # Stop timing here
        

    return "time_elapsed"
        

def master_test(quantity: int, jamf_instance_name: str, policy_payload_filename: str):
    out = []
    driver = new_driver(f"https://{jamf_instance_name}.jamfcloud.com")
    client = new_jamf_client()
    for i in range(quantity):
        duration = single_timed_policy_propogation_test(
            jamf_client=client,
            driver=driver,
            policy_payload_filename=policy_payload_filename
        )
        out.append({
            "time_to_create": duration
        })

    master_test_to_csv(out)


def master_test_to_csv(master_test_data):
    pass


def main():
    master_test(50)


main()
