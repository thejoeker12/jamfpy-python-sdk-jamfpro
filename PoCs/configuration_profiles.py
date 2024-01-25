"""PoC for configuration profiles"""

import sys
import os
import xml.etree.ElementTree as ET
from pprint import pprint

# pylint: disable=wrong-import-position

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Setup Complete

# import jamfpi
# import plistlib

# with open("escaped.mobileconfig", "rb") as file:
#     load = plistlib.load(file)
#     load["PayloadDescription"] = "This is not a new description"
#     pprint(load)
#     with open("a saved profile.mobileconfig", "wb") as save:
#         plistlib.dump(load, save)
