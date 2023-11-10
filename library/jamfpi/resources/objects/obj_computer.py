"""Objects container for Jamf operations"""

class Computer:
    def __init__(self, tenant: str, serial: str, jamfid: str, raw: str):
        self.tenant = tenant
        self.serial = serial
        self.jamfid = jamfid
        self.raw = raw


    def __str__(self):
        return f"Computer with Serial: {self.serial} in {self.tenant}, {self.jamfid}"

    def rename():
        pass