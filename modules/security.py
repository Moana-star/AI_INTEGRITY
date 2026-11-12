"""Shared security extensions for the EIMS Flask application."""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# The application configures a shared Redis-compatible storage URI for production.
# The in-memory backend is intentionally limited to local development and tests.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=True,
)
