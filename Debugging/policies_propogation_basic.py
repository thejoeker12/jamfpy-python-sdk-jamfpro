import requests
import base64

INSTANCE_NAME = ""
USERNAME = ""
PASSWORD = ""
ITERATIONS = 10
INGRESS_VALUES = []

def get_bearer_token(basic_credentials, cloud_tenant_name) -> dict:
    """Accepts basic credentials and jamf instance strings, returns barer token"""
    endpoint = "/api/v1/auth/token"
    token_url = f"https://{INSTANCE_NAME}.jamfcloud.com" + endpoint
    headers = {"Authorization": f"Basic {basic_credentials}"}
    token_request = requests.post(token_url, headers=headers, timeout=10)
    if token_request.ok:
        return token_request.json()

    raise requests.HTTPError(f"Bad response: {token_request.status_code}\n{token_request.text}")


def main():
    for i in range(ITERATIONS):
        basic_token = base64.b64encode(bytes(f"{USERNAME}:{PASSWORD}", "UTF-8")).decode()
        token = get_bearer_token(basic_token, INSTANCE_NAME)["token"]
        session = requests.Session()
        headers = {
            "accept": "text/xml",
            "Authorization": f"Bearer {token}"
        }
        raw_req = requests.Request("GET", f"https://{INSTANCE_NAME}.jamfcloud.com/JSSResource/policies", headers=headers)
        prepped = session.prepare_request(raw_req)
        resp = session.send(prepped)
        print(resp)
        print(session.cookies.get_dict())
        # ingress_cookie_value = session.cookies.get_dict()
        # INGRESS_VALUES.append(ingress_cookie_value)



main()

INGRESS_VALUES = list(set(INGRESS_VALUES))
print(INGRESS_VALUES)
print(len(INGRESS_VALUES))