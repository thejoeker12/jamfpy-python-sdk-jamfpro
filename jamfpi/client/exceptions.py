"""Custom exceptions"""

class JamfAPIError(Exception):
    """Jamf API Specific error"""


class JamfPiConfigError(Exception):
    """Module Configuration error"""


class JamfPiInitError(Exception):
    """Module initiation error"""


class JamfAuthError(Exception):
    """Module Auth error"""
