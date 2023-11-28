"""Custom exception"""

class JamfAPIError(Exception):
    """Jamf API Specific error"""



class ConfigError(Exception):
    """Module Configuration error"""



class InitError(Exception):
    """Module initiation error"""


class AuthError(Exception):
    """Module Auth error"""