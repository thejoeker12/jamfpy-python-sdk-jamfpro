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

