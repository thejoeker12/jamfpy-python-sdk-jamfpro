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

