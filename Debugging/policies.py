"""PoC for configuration profiles"""
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

# Helpers

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

    return policy_id, policy_name


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

def new_chrome_webdriver(init_url: str, options: webdriver.ChromeOptions = None) -> dict:
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
def get_policy_page_source(driver: webdriver.Chrome, policy_jamf_id: str, wait_time: int = 5):
    driver.get(f"https://lbgsandbox.jamfcloud.com/policies.html?id={policy_jamf_id}")
    while wait_time > 0:
        print(f"waiting.. {wait_time}")
        time.sleep(1)
        wait_time -= 1


def check_not_found(driver: webdriver.Chrome):
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


def get_policy_page_status(driver: webdriver.Chrome, policy_name, poll_interval_time: int = 1, max_polls: int = 10) -> tuple[str, int]:
    loading_poll_count = 0
    is_missing_count = 0
    is_missing = False
    is_found = False
    iteration_count = 0

    while not is_found:

        is_missing = check_not_found(driver)
        if is_missing:
            is_missing_count += 1

        if is_missing_count >= max_polls:
            return "error - never found", None, None

        is_found = check_found(driver, policy_name)
        if is_found:
            break
        
        if not is_missing:
            loading_poll_count += 1
            if loading_poll_count >= max_polls:
                return "error", loading_poll_count, None
    
        iteration_count += 1
        if iteration_count >= max_polls:
            return "error", iteration_count, 0
        
        print(f"Iteration: {iteration_count}\nis_missing: {is_missing}\nis_found: {is_found}\nloading_poll_count: {loading_poll_count}")

        time.sleep(poll_interval_time)

    
    total_load_time = loading_poll_count * poll_interval_time
    total_missing_time = (iteration_count - loading_poll_count) * poll_interval_time
    print(f"Total load time: {total_load_time} seconds")
    print(f"Total missing time: {total_missing_time} seconds")

    if is_missing:
        return "missing", total_load_time, total_load_time
    
    if is_found:
        return "found", total_load_time, total_missing_time


def single_timed_policy_propogation_test(driver: webdriver.Chrome, jamf_client: jamfpi.JamfTenant, policy_payload_filename, policy_name):
    policy_id, policy_name = make_from_file(
        save=False,
        client=jamf_client,
        payload_filename=policy_payload_filename
    )

    status, a, b = get_policy_page_status(driver, policy_name, 0.5, 10)
        
    return "time_elapsed"


def master_test(quantity: int, jamf_instance_name: str, policy_payload_filename: str):
    out = []
    driver = new_chrome_webdriver(f"https://{jamf_instance_name}.jamfcloud.com")
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
    driver = new_chrome_webdriver("https://lbgsandbox.jamfcloud.com")

    get_policy_page_source("310", driver, wait_time=1)
    result = get_policy_page_status(driver, "Test From Python-917")
    print(result)

    get_policy_page_source("312", driver, wait_time=1)
    result = get_policy_page_status(driver, "Test From Python-917")
    print(result)

    close_driver_with_input(driver)


main()
