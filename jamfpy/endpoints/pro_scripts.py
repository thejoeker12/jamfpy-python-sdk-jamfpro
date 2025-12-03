"""Endpoint module for managing Jamf Pro scripts."""

from requests import Request
from ..client.exceptions import JamfAPIError
from .models import ProEndpoint

class Scripts(ProEndpoint):
    """Endpoint for managing scripts in the modern Jamf Pro API (v1+)."""
    _uri = "/scripts"
    _name = "scripts"

    def get_all(self):
        """Get all scripts from the Jamf Pro API."""
        page_size = 200
        page_number = 0
        suffix_template = f"/scripts?page={page_number}&page-size={page_size}&sort=name%3Aasc"
        base_url = self._api.url("1")
        headers = self._api.header("read")["json"]

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

        return resp


    def get_by_id(self, target_id: int):
        """Get a script by its ID."""
        return self._api.do(
            Request(
                "GET",
                url=self._api.url("1") + f"{self._uri}/{target_id}",
                headers=self._api.header("read")["json"]

            )
        )


    def delete_by_id(self, target_id: int):
        """Delete a script by its ID."""
        return self._api.do(Request(
            method="DELETE",
            url=self._api.url("1") + f"{self._uri}/{target_id}")
        )
