
from requests import Request
from ..client.exceptions import JamfAPIError
from .endpoint_parent import Endpoint



class Scripts(Endpoint):
    _uri = "/scripts"

    def get_all(self):
        
        page_size = 200
        page_number = 0
        suffix_template = f"/scripts?page={page_number}&page-size={page_size}&sort=name%3Aasc"
        base_url = self._api.url("1")
        headers = self._api.header("basic")

        url = base_url + suffix_template.format(page_number=page_number, page_size=page_size)
        req = Request("GET", url=url, headers=headers)
        resp = self._api.do(req)

        # // NOTE this is where your current page logic is
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
            url = base_url + suffix_template.format(page_number=page_number, page_size=page_size)
            req = Request("GET", url=url, headers=headers)
            resp = self._api.do(req)
            if resp.ok:
                resp_json = resp.json()
                resp_len = len(resp_json["results"])
                for i in resp_json["results"]:
                    out_list.append(i)
            else:
                raise JamfAPIError(f"Bad call on page: {page_number}")

        return resp, out_list




    def get_by_id(self, target_id: int):
        
        url = self._api.url("1") + f"{self._uri}/{target_id}"
        headers = self._api.header("basic")
        req = Request("GET", url=url, headers=headers)
        resp = self._api.do(req)
        if resp.ok:
            return (resp, None)

        return resp, None

    
    def delete_by_id(self, target_id: int):
        
        url = self._api.url("1") + f"{self._uri}/{target_id}"
        headers = self._api.header("basic")
        req = Request("DELETE", url=url, headers=headers)
        resp = self._api.do(req)
        if resp.ok:
            return (resp, None)

        return resp


    # def create(
    #         name: str,
    #         info: str = None,
    #         notes: str = None,
    #         priority: str = None
    # ):
    #     pass
