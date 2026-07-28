"""Pure-Python SQLCipher 4 key derivation and page verification.

This module deliberately has no process, filesystem, or network access.  A
future Windows capture helper can pass an in-memory passphrase here without
coupling key handling to the connector or API layers.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from pathlib import Path

PAGE_SIZE = 4096
RESERVE_SIZE = 80
SALT_SIZE = 16
IV_SIZE = 16
HMAC_SIZE = 64
KEY_SIZE = 32
KDF_ITERATIONS = 256_000


def derive_database_key(passphrase: bytes, salt: bytes) -> bytes:
    """Derive a SQLCipher 4 database key from a captured passphrase."""

    if not passphrase:
        raise ValueError("passphrase must not be empty")
    if len(salt) != SALT_SIZE:
        raise ValueError(f"salt must be {SALT_SIZE} bytes")
    return hashlib.pbkdf2_hmac("sha512", passphrase, salt, KDF_ITERATIONS, dklen=KEY_SIZE)


def _derive_page_mac_key(database_key: bytes, salt: bytes) -> bytes:
    mac_salt = bytes(value ^ 0x3A for value in salt)
    return hashlib.pbkdf2_hmac("sha512", database_key, mac_salt, 2, dklen=KEY_SIZE)


def verify_page_one(page: bytes, database_key: bytes) -> bool:
    """Verify SQLCipher page-one HMAC without decrypting or writing a page."""

    if len(page) != PAGE_SIZE or len(database_key) != KEY_SIZE:
        return False
    salt = page[:SALT_SIZE]
    hmac_data_end = PAGE_SIZE - RESERVE_SIZE + IV_SIZE
    hmac_data = page[SALT_SIZE:hmac_data_end]
    expected = page[-HMAC_SIZE:]
    mac = hmac.new(_derive_page_mac_key(database_key, salt), digestmod=hashlib.sha512)
    mac.update(hmac_data)
    mac.update(struct.pack("<I", 1))
    return hmac.compare_digest(mac.digest(), expected)


def read_page_one(path: str | Path) -> bytes:
    """Read exactly one encrypted page for an explicit caller-selected file."""

    with Path(path).open("rb") as handle:
        page = handle.read(PAGE_SIZE)
    if len(page) != PAGE_SIZE:
        raise ValueError("database does not contain a complete first page")
    return page


def derive_verified_key(passphrase: bytes, page_one: bytes) -> bytes | None:
    """Derive a key and return it only when page-one verification succeeds."""

    if len(page_one) != PAGE_SIZE:
        raise ValueError("page_one must be exactly one SQLCipher page")
    key = derive_database_key(passphrase, page_one[:SALT_SIZE])
    return key if verify_page_one(page_one, key) else None
