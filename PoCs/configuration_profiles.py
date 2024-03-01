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
import logging

config = jamfpi.import_json("clientauth.json")

client = jamfpi.init_client(
    tenant_name="lbgsandbox",
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=logging.WARN
)

def test_in_out_key():
    RANDOM_NUMBER = random.randint(10, 10000)
    NEW_PROFILE_NAME = f"Test Profile Nothing {RANDOM_NUMBER}"
    print(f"Sending All Computers as: {False}")

    # Create New
    new_profile_payload = open("payload.mobileconfig", "r").read().format(NAME=NEW_PROFILE_NAME, ALL_COMPUTERS=False)
    print(new_profile_payload)
    create_new_profile = client.classic.configuration_profiles.create(new_profile_payload, "json")

    # Get ID from creation
    if create_new_profile.ok:
        root = ElementTree.fromstring(create_new_profile.text)
        new_profile_id = root.find('id').text
        print(f"Created new profile with id: {new_profile_id}")
    else:
        raise Exception("Failed to make profile")
    
    # Get profile and check all_computers
    get_profile = client.classic.configuration_profiles.get_by_id(new_profile_id, "json")
    get_profile_json = get_profile.json()
    all_computers = get_profile_json["os_x_configuration_profile"]["scope"]["all_computers"]
    print(f"Received All Computers as: {all_computers}")

    # Send update to flip the bool
    print("Switching")
    new_profile_payload = open("payload.mobileconfig", "r").read().format(NAME=NEW_PROFILE_NAME, ALL_COMPUTERS=True)
    print(new_profile_payload)
    update_switch = client.classic.configuration_profiles.update_by_id(new_profile_id, new_profile_payload)

    # Check update ok
    if update_switch.ok:
        print("Switched successfully")
        get_profile = client.classic.configuration_profiles.get_by_id(new_profile_id, "json")
        get_profile_json = get_profile.json()
        all_computers = get_profile_json["os_x_configuration_profile"]["scope"]["all_computers"]
        print(f"Swtiched All Computers as: {all_computers}")

    

    # Cleanup

    print("Cleaning up...")
    delete_profile = client.classic.configuration_profiles.delete_by_id(new_profile_id)
    if delete_profile.ok:
        print("Deleted profile successfully")
    else: 
        raise Exception("Failed to delete profile")
    


def cleanup():
    all_profiles = client.classic.configuration_profiles.get_all("json")
    if all_profiles.ok:
        pprint(all_profiles.json())
    else:
        raise Exception("Failed to get all profiles")
    
    for profile in all_profiles.json()["os_x_configuration_profiles"]:
        profile_id = profile["id"]
        print(f"Deleting profile {profile_id}")
        delete_profile = client.classic.configuration_profiles.delete_by_id(profile_id)
        if delete_profile.ok:
            print(f"Deleted profile {profile_id} successfully")
        else:
            raise Exception(f"Failed to delete profile {profile_id}")


def main():
    test_in_out_key()


main()