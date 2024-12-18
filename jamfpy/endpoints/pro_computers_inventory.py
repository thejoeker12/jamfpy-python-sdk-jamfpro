"""Endpoints for Jamf Pro Computers Inventory"""

from pathlib import Path
from requests import Request
from .endpoint_parent import Endpoint
from ..client.utility import create_single_file_payload


class ComputersInventory(Endpoint):
    _uri = "/computers-inventory"

    def upload_attachment(self, computer_id: int, filepath: Path):
        url = self._api.url(1) + self._uri + f"/{computer_id}/attachments"
        headers = self._api.header("read")["json"]
        payload = create_single_file_payload(filepath, filepath.name, filepath.suffix)
        req = Request("POST", url=url, headers=headers, files=payload)
        return self._api.do(req)
