import jamfpi
import random
from requests import Request, HTTPError

CLOUD_TENANT_NAME = ""
CLIENT_ID = ""
CLIENT_SECRET = ""
TEXT_PATH = ""

instance = jamfpi.init_client(
    tenant_name=CLOUD_TENANT_NAME,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
)

def call(target_id):
    req = Request(
        method="GET",
        url=instance.pro.url(1) + f"/dock-items/{target_id}",
        headers=instance.pro.header("basic")
    )

    return req

text = open(TEXT_PATH, "r").read()
out = []
calls = 0
text_index = 0
while calls < 1000:
    text_split = text.lower().split()
    user_try = str(input(": "))
    
    if text_index == len(text_split):
        text_index = 0

    elif user_try == text_split[text_index]:
        print("Success! :")
        text_index += 1
        i = random.randint(1, 1000)
        calls += 1
        try:
            resp = call(i)
            if resp.ok:
                out.append(resp.json())

        except HTTPError as e:
            print(f"Dock-item with ID: {i} does not exist\nBad Luck!")

    elif user_try == "q":
        break

    else:
        print("Wrong!")

for i in out:
    print(i)