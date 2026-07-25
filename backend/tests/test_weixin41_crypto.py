import hashlib
import hmac
import struct

from app.connectors.weixin41_crypto import (
    HMAC_SIZE,
    PAGE_SIZE,
    RESERVE_SIZE,
    SALT_SIZE,
    derive_database_key,
    derive_verified_key,
    verify_page_one,
)


def make_page_one(passphrase: bytes) -> bytes:
    salt = bytes(range(SALT_SIZE))
    database_key = derive_database_key(passphrase, salt)
    payload = bytes((index * 17) % 256 for index in range(PAGE_SIZE - SALT_SIZE - RESERVE_SIZE))
    iv = bytes(range(16))
    page_without_hmac = salt + payload + iv + bytes(HMAC_SIZE)
    mac_salt = bytes(value ^ 0x3A for value in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", database_key, mac_salt, 2, dklen=32)
    signature = hmac.new(
        mac_key,
        page_without_hmac[SALT_SIZE : PAGE_SIZE - RESERVE_SIZE + 16] + struct.pack("<I", 1),
        hashlib.sha512,
    ).digest()
    return page_without_hmac[:-HMAC_SIZE] + signature


def test_derives_sqlcipher4_key_with_expected_vector():
    assert derive_database_key(bytes(range(32)), bytes(range(16))).hex() == (
        "d6d2e116eae459f966d0f24ffeba9c0eca5f0c66c4574816378c04dae2425862"
    )


def test_verifies_synthetic_page_one_and_rejects_wrong_key():
    passphrase = b"synthetic-passphrase-for-protocol"
    page = make_page_one(passphrase)
    database_key = derive_database_key(passphrase, page[:SALT_SIZE])

    assert verify_page_one(page, database_key)
    assert not verify_page_one(page, bytes(reversed(database_key)))


def test_derive_verified_key_returns_only_hmac_validated_key():
    passphrase = b"synthetic-passphrase-for-protocol"
    page = make_page_one(passphrase)

    assert derive_verified_key(passphrase, page) == derive_database_key(passphrase, page[:SALT_SIZE])
    assert derive_verified_key(b"wrong-passphrase", page) is None
