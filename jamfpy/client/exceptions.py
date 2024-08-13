"""Custom exceptions"""

class JamfAPIError(Exception):
    """Jamf API Specific error"""


class jamfpyConfigError(Exception):
    """Module Configuration error"""


class jamfpyInitError(Exception):
    """Module initiation error"""


class JamfAuthError(Exception):
    """Module Auth error"""
