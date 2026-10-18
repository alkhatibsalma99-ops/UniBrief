
import os
import secrets
import hashlib

from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import JWTError, jwt
from pwdlib import PasswordHash


# ==========================================
# ENVIRONMENT CONFIGURATION
# ==========================================

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY must be configured with "
        "a strong random value of at least 32 characters."
    )

ALGORITHM = "HS256"

# Access Token: 60 minutes
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Refresh Token: 30 days
REFRESH_TOKEN_EXPIRE_DAYS = 30


# ==========================================
# PASSWORD HASHING
# ==========================================

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        plain_password,
        hashed_password,
    )


# ==========================================
# ACCESS TOKEN CREATION
# ==========================================

def create_access_token(data: dict) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire
    })

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


# ==========================================
# ACCESS TOKEN VALIDATION
# ==========================================

def decode_access_token(token: str):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        return payload

    except JWTError:
        return None


# ==========================================
# REFRESH TOKEN CREATION
# ==========================================

def create_refresh_token() -> str:
    """
    Generate a cryptographically secure
    random refresh token.
    """
    return secrets.token_urlsafe(48)


# ==========================================
# REFRESH TOKEN HASHING
# ==========================================

def hash_refresh_token(token: str) -> str:
    """
    Hash the refresh token before storing
    it in the database.
    """
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


# ==========================================
# REFRESH TOKEN EXPIRATION
# ==========================================

def get_refresh_token_expiry() -> datetime:
    """
    Return the expiration time
    of a new refresh token.
    """
    return datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )


# ==========================================
# CURRENT UTC TIME
# ==========================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)
