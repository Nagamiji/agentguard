from keel.security import KEY_PREFIX, generate_api_key, hash_api_key


def test_generated_key_has_prefix_and_entropy() -> None:
    full_key, prefix, key_hash = generate_api_key()
    assert full_key.startswith(f"{KEY_PREFIX}_")
    assert prefix == full_key[:12]
    assert len(full_key) > 40  # 256 bits of entropy, url-safe encoded
    assert len(key_hash) == 64


def test_hash_is_deterministic_and_not_reversible_from_storage() -> None:
    full_key, _, key_hash = generate_api_key()
    assert hash_api_key(full_key) == key_hash
    # The stored hash must never contain the key itself.
    assert full_key not in key_hash


def test_keys_are_unique() -> None:
    keys = {generate_api_key()[0] for _ in range(100)}
    assert len(keys) == 100
