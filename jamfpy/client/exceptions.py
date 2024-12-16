"""Custom exceptions"""

class JamfAPIError(Exception):
    """Jamf API Specific error"""


class JamfpyConfigError(Exception):
    """Module Configuration error"""


class JamfpyInitError(Exception):
    """Module initiation error"""


class JamfAuthError(Exception):
    """Module Auth error"""
