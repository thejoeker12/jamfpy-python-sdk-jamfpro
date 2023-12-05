from requests import Request
from ...client.exceptions import *



class Scripts:
    def __init__(self, api):
        from ...client.api import API
        self.api: API = api

    def getAll(self):
        page_size = 200
        page_number = 0
        suffix_template = "/scripts?page={page_number}&page-size={page_size}&sort=name%3Aasc"
        base_url = self.api.url("1")
        headers = self.api.header("basic")

        url = base_url + suffix_template.format(page_number=page_number, page_size=page_size)
        req = Request("GET", url=url, headers=headers)
        resp = self.api.do(req)

        out_list = []
        if resp.ok:
            resp_json = resp.json()
            resp_len = len(resp_json["results"])
            for i in resp_json["results"]:
                out_list.append(i)
            if resp_len < page_size:
                return resp, resp_json["results"]
            
        else:
            raise JamfAPIError("problem")
        
        
        while resp_len != 0:
            page_number += 1
            print(page_number)
            url = base_url + suffix_template.format(page_number=page_number, page_size=page_size)
            req = Request("GET", url=url, headers=headers)
            resp = self.api.do(req)
            if resp.ok:
                resp_json = resp.json()
                resp_len = len(resp_json["results"])
                for i in resp_json["results"]:
                    out_list.append(i)
            else:
                raise JamfAPIError("Bad call on page: %s", page_number)
            
        return resp, out_list

            


    def getByID(self, id):
        suffix = f"/scripts/{id}"
        url = self.api.url("1") + suffix
        print(url)
        headers = self.api.header("basic")
        req = Request("GET", url=url, headers=headers)
        resp = self.api.do(req)
        if resp.ok:
            return (resp, None)

        return resp, None
    

    def create(
            name: str,
            info: str = None,
            notes: str = None,
            priority: str = None
    ):
        pass