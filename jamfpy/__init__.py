"""Master init for jamfpy Library"""

from .client.auth import OAuth, BasicAuth
from .client.client import API, ProAPI, ClassicAPI
from .client.tenant import Tenant
from .client.logger import new_logger
