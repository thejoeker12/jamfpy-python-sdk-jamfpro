"""Endpoints for Jamf Pro Computers Inventory"""

from ..endpoint_parent import Endpoint
from ...client.utility import create_single_file_payload
from pathlib import Path
from requests import Request

class ComputersInventory(Endpoint):
    suffix = "/computers-inventory"

    def upload_attachment(self, computer_id: int, filepath: Path):
        url = self._api.url(1) + self.suffix + f"/{computer_id}/attachments"
        headers = self._api.header("basic")
        payload = create_single_file_payload(filepath, filepath.name, filepath.suffix)
        req = Request("POST", url=url, headers=headers, files=payload)
        resp = self._api.do(req)
        return resp