"""Custom exception classes for handling Jamf Pro API-specific errors and edge cases."""

class JamfAPIError(Exception):
    """Jamf API Specific error"""


class jamfpyConfigError(Exception):
    """Module Configuration error"""


class JamfpyInitError(Exception):
    """Module initiation error"""


class JamfAuthError(Exception):
    """Module Auth error"""
