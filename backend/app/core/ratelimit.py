"""
Shared slowapi rate limiter instance.

Defined in its own module (instead of inside app.server) so that routers
such as app.api.chat can import the limiter without triggering a circular
import: app.server imports the routers at the bottom, after the FastAPI app
is created, while this module only depends on slowapi.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# key_func defaults to the client's remote address. Per the project config
# this is used for both the per-IP limit and the (per-IP) global limit.
limiter = Limiter(key_func=get_remote_address)
