"""
Crude script for figuring out how many endpoints a Jamf tenant has
"""

import requests
from pprint import pprint
import json
TENANT = ""
CLASSIC_SCHEMA_URL = f"https://{TENANT}.jamfcloud.com/classicapi/doc/swagger.json"
CLASSIC_JSON_SCHEMA_NAME = "JSONTEST.json"
PRO_SCHEMA_URL = f"https://{TENANT}.jamfcloud.com/api/schema/"

def get_pro():
    """Retrieve Pro Schema from web location"""
    req = requests.get(PRO_SCHEMA_URL)
    
    if req.ok:
        return req.json()
    
    else:
        raise requests.HTTPError("Bad request", req, req.text)


def read_classic():
    """Read classic schema from file as web version currently broken"""
    with open(f"misc/{CLASSIC_JSON_SCHEMA_NAME}.json", "r") as file:
        data = json.load(file)

    return data


def json_to_file(pro_data, api):
    """Write JSON to file"""
    method_types = []
    master = {}
    for path in pro_data["paths"]:
        methods = []
        key = path
        for method in pro_data["paths"][key]:
            method=method.replace(" ", "")
            methods.append(method)
            if method not in method_types:
                method_types.append(method)
        
        master[key] = methods

    with open(f"output-{api}.csv", "w") as file:
        file.write("url,api,get,post,put,patch,delete\n")
        for endpoint in master:
            
            get = "False" if "get" in master[endpoint] else "N/A"
            delete = "False" if "delete" in master[endpoint] else "N/A"
            post = "False" if "post" in master[endpoint] else "N/A"
            put = "False" if "put" in master[endpoint] else "N/A"
            patch = "False" if "patch" in master[endpoint] else "N/A"

            out_str = f"{endpoint},{api},{get},{post},{put},{patch},{delete}\n"


            file.write(out_str)


def main():
    json_to_file(get_pro(), "pro")
    json_to_file(read_classic(),"classic")




if __name__ == "__main__":
    main()

