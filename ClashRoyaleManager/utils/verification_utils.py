"""Helpers for Discord-to-Clash Royale verification."""

import secrets
import string


VERIFICATION_CODE_PREFIX = "CR"
VERIFICATION_CODE_LENGTH = 6
VERIFICATION_TTL_MINUTES = 30


def generate_verification_code() -> str:
    """Generate a short code for a member to post in Clash Royale clan chat."""
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(VERIFICATION_CODE_LENGTH))
    return f"{VERIFICATION_CODE_PREFIX}-{random_part}"
