# === ORIGIN ===
# Source: https://github.com/marketcalls/openalgo@3542a6e8f8261e79711e520edf0b7bf25bd4e315
# Vendored: 2026-08-01 by scripts/sync_vendor.py
# License: AGPL-3.0 (private-use absorption; see vendor/openalgo/README.md)
# Do not edit directly - re-run sync_vendor.py after reviewing upstream diff.
# === END ORIGIN ===
# Dhan API Base URL Configuration

# Base URL for Dhan API endpoints
BASE_URL = "https://api.dhan.co"


# Function to build full URL with endpoint
def get_url(endpoint):
    """
    Constructs a full URL by combining the base URL and the endpoint

    Args:
        endpoint (str): The API endpoint path (should start with '/')

    Returns:
        str: The complete URL
    """
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return BASE_URL + endpoint
