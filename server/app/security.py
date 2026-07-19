import hashlib
import hmac
import secrets


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    iters = 200_000
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iters)
    return f"pbkdf2${iters}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def new_submit_token() -> str:
    return "vs_" + secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

