# pylint: disable=wrong-import-position, unused-import, R0801

# Dir specific setup rubbish

import sys
import os

this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
sys.path.append(parent_dir)

# Script

import jamfpi
CLIENT_NAME = ""
USERNAME = ""
PASSWORD = ""
ITERATION_COUNT = 10

client = jamfpi.init_client(
    tenant_name=CLIENT_NAME,
    username=USERNAME,
    password=PASSWORD
)

def main():
    ingress_list = []
    for i in range(ITERATION_COUNT):
        client = jamfpi.init_client(
            tenant_name=CLIENT_NAME,
            username=USERNAME,
            password=PASSWORD
        )
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


    print(out_dict)


main()
