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

def get_jamf_client(client: jamfpi.JamfTenant) -> jamfpi.JamfTenant:

    config = jamfpi.import_json("clientauth.json")

    client = jamfpi.init_client(
        tenant_name="lbgsandbox",
        client_id=config["clientId"],
        client_secret=config["clientSecret"],
        logging_level=logging.INFO
    )

    return client


def delete_all():
    client = get_jamf_client()
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


def make_from_file(save: bool, client: jamfpi.JamfTenant):
    policy_name = f"Test From Python-{random.randint(1,10000)}"
    policy = open("policy_payload.xml", "r").read()
    policy_with_name = policy.format(NAME=policy_name)
    print(f"Name: {policy_name}")

    create_policy = client.classic.policies.create(policy_with_name)

    xml_data = create_policy.text
    root = ElementTree.fromstring(xml_data)
    id_number = root.find("id").text

    if save:
        get_save_json(id_number, policy_name)


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

def get_driver(init_url: str) -> dict:
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)

    driver = webdriver.Chrome(options=options)
    driver.get(init_url)


    input("Press enter after logging in...")

    return driver


def get_policy_page_source(policy_jamf_id, driver: webdriver.Chrome, wait_time: int = 5):
    driver.get(f"https://lbgsandbox.jamfcloud.com/policies.html?id={policy_jamf_id}&o=r")
    time.sleep(5)
    return driver.page_source


def close_driver_with_input(driver: webdriver.Chrome):
    input("Press enter to close driver: ")
    driver.close()


def parse_page(html_text) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    print(soup.text)
    with open("out.html", "w") as file:
        file.write(str(soup))

    if 'class="code">404</h1>' in str(soup):
        return("This page was not found!: ")

    return "this page was found!: "


def main():
    # connect_to_driver_from_file("session_info.json")
    driver = get_driver("https://lbgsandbox.jamfcloud.com")
    for i in [310, 311, 312]:
        print("\n--------")
        page_html = get_policy_page_source(i, driver)
        found_text = parse_page(page_html)
        print(found_text + str(i))
        print("\n--------")
    close_driver_with_input(driver)




main()

# def connect_to_driver_from_arg(session_info):
#     driver = webdriver.Remote(command_executor=session_info["executor_url"])
#     driver.session_id = session_info["session_id"]
#     return driver


# def connect_to_driver_from_file(filename):
#     with open(filename, "r") as file:
#         session_info = json.loads(file.read())

#     executor_url = session_info["executor_url"]
#     session_id = session_info["session_id"]

#     options = webdriver.ChromeOptions()
#     options.add_experimental_option("detach", True)
#     driver = webdriver.Remote(command_executor=executor_url, options=options)
#     driver.session_id = session_id


# def connect_to_chrome():
#     options = webdriver.ChromeOptions()
#     options.add_argument("--remote-debugging-port=9222")
#   