"""Password hashing with stdlib `hashlib.scrypt` (per-user random salt).

No native build or extra crypto dependency is needed. The stored format is
`scrypt$<salt_hex>$<hash_hex>`.
"""

import hashlib
import hmac
import os

# scrypt cost parameters. n=2**14, r=8, p=1 uses ~16 MB, under the default
# 32 MB limit, so no `maxmem` override is needed.
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return hmac.compare_digest(dk.hex(), hash_hex)
