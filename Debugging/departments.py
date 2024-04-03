"""PoC for configuration profiles"""
# pylint: disable=wrong-import-position, unused-import, R0801

import sys
import os
import xml.etree.ElementTree as ET
from pprint import pprint



this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

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

config = jamfpi.import_json("clientauth.json")

APP1 = "cb9c9769c9f87d32"
APP2 = "f248e7b703882ffc"

client = jamfpi.init_client(
    tenant_name="lbgsandbox",
    client_id=config["clientId"],
    client_secret=config["clientSecret"],
    logging_level=logging.INFO
)

POLICY_NAMES = []
def make_from_file(
        client: jamfpi.JamfTenant, 
        filename: str = "policy_payload.xml"
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

    return policy_id, policy_name, create_policy

client.classic._session.cookies.set("jpro-ingress", APP2)
client.classic.policies.delete_by_id(982)
