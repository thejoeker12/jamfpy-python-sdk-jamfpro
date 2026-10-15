"""Master init for jamfpy Library"""

from .client.auth import OAuth, BasicAuth
from .client.api import API
from .client.client import ProAPI, ClassicAPI
from .client.tenant import Tenant
from .client.logger import new_logger

__all__ = ["Tenant", "OAuth", "BasicAuth", "API", "ProAPI", "ClassicAPI", "new_logger"]
