"""Password hashes: scrypt from the stdlib, stored as scrypt$n$r$p$salt$hash (hex)."""
import hashlib
import hmac
import os

N, R, P = 2 ** 14, 8, 1
NO_PASSWORD = '!'  # stored for accounts nobody logs in to (simulations, bots), check_password refuses it


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode('latin-1'), salt=salt, n=N, r=R, p=P)
    return 'scrypt${}${}${}${}${}'.format(N, R, P, salt.hex(), digest.hex())


def check_password(password, stored):
    try:
        method, n, r, p, salt, digest = stored.split('$')
    except ValueError:
        return False
    if method != 'scrypt':
        return False
    actual = hashlib.scrypt(password.encode('latin-1'), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(actual, bytes.fromhex(digest))
