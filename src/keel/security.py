import hashlib
import secrets

KEY_PREFIX = "ag"
_SECRET_BYTES = 32
_PREFIX_LEN = 12


def hash_api_key(full_key: str) -> str:
    """Hash an API key for storage/lookup.

    SHA-256 is the correct primitive here: API keys are high-entropy (256-bit),
    so they are not brute-forceable and need no salt/stretching. Password hashes
    (bcrypt/argon2) exist for *low*-entropy secrets and would add latency to
    every authenticated request.
    """
    return hashlib.sha256(full_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, key_hash).

    The full key is returned to the caller exactly once and never stored.
    The prefix is stored to let humans identify a key without revealing it.
    """
    full_key = f"{KEY_PREFIX}_{secrets.token_urlsafe(_SECRET_BYTES)}"
    return full_key, full_key[:_PREFIX_LEN], hash_api_key(full_key)
