"""Endpoint module for managing Jamf Pro MDM commands."""
from requests import Request, Response
from .models import ProEndpoint

class MDMCommands(ProEndpoint):
    """Endpoint for managing MDM commands in the modern Jamf Pro API (v1+)."""
    _uri = "/mdm/commands"
    _name = "mdm_commands"

    # Send the command

    def send_command(self, command_type: str, management_ids: list[str], **kwargs) -> Response:
        """
        Send a generic MDM command.

        Args:
            command_type: e.g. "DEVICE_LOCK", "ERASE_DEVICE", etc.
            management_ids: List of Jamf Pro management IDs to target.
            **kwargs: Additional fields (like pin, message, preserveDataPlan).
        """        
        payload = {
            "clientData": [{"managementId": mid} for mid in management_ids],
            "commandData": {"commandType": command_type, **kwargs},
        }

        return self._api.do(Request(
            method="POST",
            url=self._api.url("2") + self._uri,
            headers=self._api.header("read")["json"],
            json=payload)
        )

    # Convience Wrappers:

    def apply_redemption_code(self, management_ids: list[str], identifier: str, redemption_code: str) -> Response:
        """Send a APPLY_REDEMPTION_CODE command"""
        return self.send_command(
            "APPLY_REDEMPTION_CODE",
            management_ids if isinstance(management_ids, list) else [management_ids],
            identifier=identifier,
            redemptionCode=redemption_code
        )

    def certificate_list(self, management_ids: list[str]) -> Response:
        """Send a CERTIFICATE_LIST command"""

        return self.send_command(
            "CERTIFICATE_LIST",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def clear_passcode(self, management_ids: list[str], unlock_token: str) -> Response:
        """Send a CLEAR_PASSCODE command"""

        return self.send_command(
            "CLEAR_PASSCODE",
            management_ids if isinstance(management_ids, list) else [management_ids],
            unlockToken = unlock_token
        )

    def clear_restrictions_password(self, management_ids: list[str]) -> Response:
        """Send a CLEAR_RESTRICTIONS_PASSWORD"""

        return self.send_command(
            "CLEAR_RESTRICTIONS_PASSWORD",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def declerative_management(self, management_ids: list[str], data: str) -> Response:
        """Send a DECLARATIVE_MANAGEMENT command"""

        return self.send_command(
            "DECLARATIVE_MANAGEMENT",
            management_ids if isinstance(management_ids, list) else [management_ids],
            data = data
        )

    def delete_user(self, management_ids: list[str], user_name: str, force_deletion: bool, delete_all_users: bool) -> Response:
        """Send a DELETE_USER command"""
        return self.send_command(
            "DELETE_USER",
            management_ids if isinstance(management_ids, list) else [management_ids],
            userName = user_name,
            forceDeletion = force_deletion,
            deleteAllUsers = delete_all_users
        )

    def device_information(self, management_ids: list[str], queries: list = None) -> Response:
        """Send a DEVICE_INFORMATION command"""
        return self.send_command(
            "DEVICE_INFORMATION",
            management_ids if isinstance(management_ids, list) else [management_ids],
            queries = queries
        )

    def device_location(self, management_ids: list[str]) -> Response:
        """Send a DEVICE_LOCATION command"""
        return self.send_command(
            "DEVICE_LOCATION",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def lock_device(self, management_ids: list[str], message: str="Device locked remotely", pin: str="1234", phone_number: str=None) -> Response:
        """Send a DEVICE_LOCK command."""
        return self.send_command(
            "DEVICE_LOCK",
            management_ids if isinstance(management_ids, list) else [management_ids],
            message=message,
            pin=pin,
            phoneNumber = phone_number
        )

    def disable_lost_mode(self, management_ids: list[str], preserve_data_plan: bool=False, disallow_proximity_setup: bool=False, return_to_service: dict=None) -> Response:
        """Send an DISABLE_LOST_MODE command"""

        if return_to_service is None:
            return_to_service = {
                "enabled": True
                }

        return self.send_command(
            "DISABLE_LOST_MODE",
            management_ids if isinstance(management_ids, list) else [management_ids],
            preserveDataPlan=preserve_data_plan,
            disallowProximitySetup=disallow_proximity_setup,
            returnToService=return_to_service
        )

    def disable_remote_desktop(self, management_ids: list[str]) -> Response:
        """Send DISABLE_REMOTE_DESKTOP command"""
        return self.send_command(
            "DISABLE_REMOTE_DESKTOP",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def enable_lost_mode(self, management_ids: list[str], lost_mode_message: str="Your device has been put into Lost Mode", lost_mode_phone: str="", lost_mode_footnote: str="") -> Response:
        """Send ENABLE_LOST_MODE command"""
        return self.send_command(
            "ENABLE_LOST_MODE",
            management_ids if isinstance(management_ids, list) else [management_ids],
            lostModeMessage=lost_mode_message,
            lostModePhone=lost_mode_phone,
            lostModeFootnote=lost_mode_footnote
        )

    def enable_remote_desktop(self, management_ids: list[str]) -> Response:
        """Send ENABLE_REMOTE_DESKTOP"""
        return self.send_command(
            "ENABLE_REMOTE_DESKTOP",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def erase_device(self, management_ids: list[str], preserve_data_plan: bool=False, disallow_proximity_setup: bool=False, pin: str="1234", obliteration_behavior: str="Default", return_to_service: dict=None) -> Response:
        """Send an ERASE_DEVICE command"""

        if return_to_service is None:
            return_to_service = {
                "enabled": True
                }

        return self.send_command(
            "ERASE_DEVICE",
            management_ids if isinstance(management_ids, list) else [management_ids],
            preserveDataPlan=preserve_data_plan,
            disallowProximitySetup=disallow_proximity_setup,
            pin=pin,
            obliterationBehavior=obliteration_behavior,
            returnToService=return_to_service
        )

    def log_out_user(self, management_ids: list[str]) -> Response:
        """Send LOG_OUT_USER command"""
        return self.send_command(
            "LOG_OUT_USER",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def managed_application_list(self, management_ids: list[str], identifiers: list[str]) -> Response:
        """SEND MANAGED_APPLICATION_LIST command"""
        return self.send_command(
            "MANAGED_APPLICATION_LIST",
            management_ids if isinstance(management_ids, list) else [management_ids],
            identifiers=identifiers
        )

    def managed_media_list(self, management_ids: list[str]) -> Response:
        """Send MANAGED_MEDIA_LIST command"""
        return self.send_command(
            "MANAGED_MEDIA_LIST",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def refresh_cellular_plans(self, management_ids: list[str], esim_server_url: str) -> Response:
        """Send REFRESH_CELLULAR_PLANS command"""
        return self.send_command(
            "REFRESH_CELLULAR_PLANS",
            management_ids if isinstance(management_ids, list) else [management_ids],
            esimServerUrl=esim_server_url
        )

    def play_lost_mode_sound(self, management_ids: list[str]) -> Response:
        """Send PLAY_LOST_MODE_SOUND command"""
        return self.send_command(
            "PLAY_LOST_MODE_SOUND",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def restart_device(self, management_ids: list[str], rebuild_kernel_cache: bool=True, kextpath: list[str]=None, notify_user: bool=True) -> Response:
        """Send RESTART_DEVICE command"""
        if rebuild_kernel_cache and kextpath is None:
            kextpath = []

        return self.send_command(
            "RESTART_DEVICE",
            management_ids if isinstance(management_ids, list) else [management_ids],
            rebuildKernalCache=rebuild_kernel_cache,
            kextPaths=kextpath,
            notifyUser=notify_user
        )

    def request_mirroring(self, management_ids: list[str], destination_device_id: str, destination_name: str, password: str=None, scan_time: str=None) -> Response:
        """Send REQUEST_MIRRORING command"""
        return self.send_command(
            "REQUEST_MIRRORING",
            management_ids if isinstance(management_ids, list) else [management_ids],
            destinationDeviceId=destination_device_id,
            destinationName=destination_name,
            password=password,
            scanTime=scan_time
        )

    def security_info(self, management_ids: list[str]) -> Response:
        """Send SECURITY_INFO command"""
        return self.send_command(
            "SECURITY_INFO",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    # Add in Settings

    def set_auto_admin_password(self, management_ids: list[str], guid: str, password: str) -> Response:
        """Send SET_AUTO_ADMIN_PASSWORD command"""
        return self.send_command(
            "SET_AUTO_ADMIN_PASSWORD",
            management_ids if isinstance(management_ids, list) else [management_ids],
            guid=guid,
            password=password
        )

    def set_recovery_lock(self, management_ids: list[str], new_password: str) -> Response:
        """Send SET_RECOVERY_LOCK command"""
        return self.send_command(
            "SET_RECOVERY_LOCK",
            management_ids if isinstance(management_ids, list) else [management_ids],
            newPassword=new_password
        )

    def stop_mirroring(self, management_ids: list[str]) -> Response:
        """Send STOP_MIRRORING command"""
        return self.send_command(
            "STOP_MIRRORING",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def shut_down_device(self, management_ids: list[str]) -> Response:
        """Send SHUT_DOWN_DEVICE command"""
        return self.send_command(
            "SHUT_DOWN_DEVICE",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def unlock_user_account(self, management_ids: list[str], username: str) -> Response:
        """Send UNLOCK_USER_ACCOUNT command"""
        return self.send_command(
            "UNLOCK_USER_ACCOUNT",
            management_ids if isinstance(management_ids, list) else [management_ids],
            userName=username
        )

    def validate_applications(self, management_ids: list[str]) -> Response:
        """Send VALIDATE_APPLICATIONS command"""
        return self.send_command(
            "VALIDATE_APPLICATIONS",
            management_ids if isinstance(management_ids, list) else [management_ids]
        )

    def validate_recovery_lock(self, management_ids: list[str], password: str) -> Response:
        """Send VALIDATE_RECOVERY_LOCK command"""
        return self.send_command(
            "VALIDATE_RECOVERY_LOCK",
            management_ids if isinstance(management_ids, list) else [management_ids],
            password=password
        )
