"""
Crude script for figuring out how many endpoints a Jamf tenant has
"""

import requests
from pprint import pprint
import json
TENANT = ""
CLASSIC_SCHEMA_URL = f"https://{TENANT}.jamfcloud.com/classicapi/doc/swagger.json"
PRO_SCHEMA_URL = f"https://{TENANT}.jamfcloud.com/api/schema/"

def get_pro():
    req = requests.get(PRO_SCHEMA_URL)
    
    if req.ok:
        return req.json()
    
    else:
        raise requests.HTTPError("Bad request", req, req.text)


def parse_pro(pro_json) -> int:
    active_counter = 0
    deprecated_counter = 0
    paths = pro_json["paths"]
    for endpoint in paths:
        for method in paths[endpoint]:
            try:
                deprecated = paths[endpoint][method]["deprecated"]
                if deprecated == "true":
                    deprecated = True
            except KeyError:
                deprecated = False

            if deprecated:
                deprecated_counter += 1

            if not deprecated:
                active_counter += 1

    print(f"Active: {active_counter}")
    print(f"Deprecated: {deprecated_counter}")



# def get_classic():
#     headers = {"accept": "application/json"}
#     req = requests.get(CLASSIC_SCHEMA_URL, headers=headers, stream=True)
#     if req.ok:
#         json_chunks = ""
#         for chunk in req.iter_content(chunk_size=8192):
#             decoded = chunk.decode('utf-8')
#             print(len(decoded))
#             json_chunks += decoded
#             file = open("JSONTEST.json", "w")
#             file.write(json_chunks)
#             file.close()

#         print(json_chunks)


def read_classic():
    with open("JSONTEST.json", "r") as file:
        data = json.load(file)

    return data

def parse_classic(clc_json):
    active_counter = 0
    deprecated_counter = 0
    paths = clc_json["paths"]
    for endpoint in paths:
        for method in paths[endpoint]:
            if "deprecated" in paths[endpoint][method]["summary"].lower():
                deprecated = True
            else:
                deprecated = False


            if deprecated:
                deprecated_counter += 1
            
            if not deprecated:
                active_counter += 1


    print(f"Active: {active_counter}")
    print(f"Deprecated: {deprecated_counter}")




        
def main():
    print("Pro:")
    parse_pro(get_pro())
    print("Classic:")
    parse_classic(read_classic())


if __name__ == "__main__":
    main()

