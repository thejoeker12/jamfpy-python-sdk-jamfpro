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
import time
from datetime import datetime
from pprint import pprint

# Helpers

POLICY_PAYLOAD_FILENAME = "policy_payload_2.xml"
OUT_FILENAME = "policies1.csv"
MAX_POLLS = 50
POLL_INTERVAL_TIME = 0.1
BUFFER_BEFORE_POLLING = 0
TEST_QUANTITY = 30
CLEANUP = True
POLICY_NAMES = []

def new_jamf_client() -> jamfpi.JamfTenant:
    """Returns new jamf client using auth from file """
    config = jamfpi.import_json("clientauth.json")

    client = jamfpi.init_client(
        tenant_name="lbgsandbox",
        client_id=config["clientId"],
        client_secret=config["clientSecret"],
        logging_level=logging.INFO
    )
    return client


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
    creation_time = datetime.now()

    xml_data = create_policy.text
    root = ElementTree.fromstring(xml_data)
    policy_id = root.find("id").text

    if save:
        get_save_json(policy_id, policy_name)
        get_save_xml(policy_id, policy_name)

    return policy_id, policy_name, creation_time


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


# Automated GUI checking

def new_chrome_webdriver(init_url: str, options: webdriver.ChromeOptions = None) -> webdriver.Chrome:
    if options == None:
        options = webdriver.ChromeOptions()
        options.add_experimental_option("detach", True)

    driver = webdriver.Chrome(options=options)
    driver.get(init_url)

    print("please log in to Jamf")
    input("press enter to continue...")

    return driver


def close_driver_with_input(driver: webdriver.Chrome):
    input("press enter to close driver...")
    driver.close()


# Replace this with a more standardised option for other resource types
def get_policy_page_source(driver: webdriver.Chrome, policy_jamf_id: str):
    print(f"gettting page source for {policy_jamf_id}")
    driver.get(f"https://lbgsandbox.jamfcloud.com/policies.html?id={policy_jamf_id}")
    wait_time = BUFFER_BEFORE_POLLING
    while wait_time > 0:
        print(f"waiting.. {wait_time}")
        time.sleep(1)
        wait_time -= 1


def check_404(driver: webdriver.Chrome):
    status_code_class_list = driver.find_elements(By.CLASS_NAME, "code")
    if len(status_code_class_list) == 0:
        return False
    
    if status_code_class_list[0].text == "404":
        return True
    
    raise Exception("neither condition met")


def check_found(driver: webdriver.Chrome, policy_name: str):
    if policy_name in driver.page_source:
        return True
    
    return False


def get_policy_page_status(driver: webdriver.Chrome, policy_name, poll_interval_time: int = 1, max_polls: int = 10):
    print(f"attempting to get page status for {policy_name}")

    """
    return pattern
    status, 
    """
    status: str = ""
    poll_count: int = 0
    message: str = ""

    poll_count: int = 0
    loading_poll_count: int = 0
    page_missing_count: int = 0

    page_missing: bool = False
    page_found: bool = False

    found_time: datetime = None
    

    while True:

        # Found
        is_found = check_found(driver, policy_name)
        if is_found:
            status = "success"
            message = "policy found"
            found_time = datetime.now()
            page_found = True
            break

        # Missing
        page_missing = check_404(driver)
        if page_missing:
            page_missing_count += 1

        if not page_missing:
            loading_poll_count += 1

        # Max polls
        poll_count += 1
        if poll_count >= max_polls:
            status = "error"
            message = "max polls threshold reached"
            break

        time.sleep(poll_interval_time)

    return_data = {
        "status": status,
        "message": message,
        "page_missing": page_missing,
        "page_found": page_found,
        "found_time": found_time,
        "poll_count": poll_count,
        "loading_poll_count": loading_poll_count,
        "page_missing_count": page_missing_count,
        "poll_interval_time": poll_interval_time
    }

    return return_data


def single_timed_policy_propogation_test(driver: webdriver.Chrome, jamf_client: jamfpi.JamfTenant):
    print(f"starting single propogation test...")

    policy_id, policy_name, creation_time = make_from_file(
        client=jamf_client,
        filename=POLICY_PAYLOAD_FILENAME,
        save=False
    )

    get_policy_page_source(driver, policy_id)
    result = get_policy_page_status(driver, policy_name, POLL_INTERVAL_TIME, MAX_POLLS)

    result["creation_time"] = creation_time
    result["creation_time_readable"] = result["creation_time"].strftime('%Y-%m-%d %H:%M:%S')

    if result["status"] == "success":
        result["time_elapsed"] = result["found_time"] - result["creation_time"]
        result["found_time_readable"] = result["found_time"].strftime('%Y-%m-%d %H:%M:%S')
        
    else:
        result["time_elapsed"] = None
        result["found_time_readable"] = None


    print("single propogation test complete")
    return result


def master_test(quantity: int, driver, client):
    print("starting master test")
    out = []
    for i in range(quantity):
        print(f"test iteration {i}")
        result = single_timed_policy_propogation_test(driver, client)
        out.append(result)

    print("test complete")

    print("cleaning up...")
    if CLEANUP:
        delete_all(client)
    return out


def write_to_csv(result_list):
    with open(OUT_FILENAME, "w") as file:
        file.write("status,message,time_elapsed,poll_count\n")
        for l in result_list:
            file.write(f"{l['status']},{l['message']},{l['time_elapsed']},{l['poll_count']}\n")


# def main():
#     client = new_jamf_client()
#     client.classic.policies.get_all()
#     cookies = client.classic._session.cookies.get_dict()
#     if cookies["jpro-ingress"] == "cb9c9769c9f87d32":
#         cookie_for_driver = "f248e7b703882ffc"
#     elif cookies["jpro-ingress"] == "f248e7b703882ffc":
#         cookie_for_driver = "cb9c9769c9f87d32"
#     else:
#         raise Exception("A new cookie!")
#     cookie_dict = {}
#     cookie_dict["name"] = "jpro-ingress"
#     cookie_dict["value"] = cookie_for_driver
#     driver = new_chrome_webdriver(f"https://lbgsandbox.jamfcloud.com")
#     driver.add_cookie(cookie_dict)
#     print(driver.get_cookies())
#     result = master_test(TEST_QUANTITY, driver, client)
#     close_driver_with_input(driver)
#     for i in result:
#         pprint(i)
#         print("\n")
#     write_to_csv(result)
#     print("complete")


def main():
    ingress_list = []
    for i in range(1):
        client = new_jamf_client()
        client.pro.scripts.get_all()
        ingress_list.append(client.pro._session.cookies.get_dict()["jpro-ingress"])
        del client

    ingress_list = list(set(ingress_list))

    for i in ingress_list:
        print(i)

    print(len(ingress_list))

    out_dict = {}
    for ingress_key in ingress_list:
        ascii_total = 0
        for char in ingress_key:
            char_ascii = ord(char)
            ascii_total += char_ascii

        out_dict[ascii_total] = ingress_key

    target = sorted(list(out_dict.keys()))[0]

    print(f"Target: {target}")
    print(out_dict[target])
    print(out_dict)

main()
