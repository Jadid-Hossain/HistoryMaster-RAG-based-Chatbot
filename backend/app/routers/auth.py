"""Authentication endpoints: register, login, me."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import database
from ..logger import get_logger
from ..security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter()
log = get_logger("historymaster.auth")

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.]{3,32}$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "created_at": user.get("created_at"),
    }


@router.post("/register", response_model=TokenResponse, summary="Create a new user account")
def register(payload: RegisterRequest):
    username = payload.username.strip()
    if not _USERNAME_PATTERN.match(username):
        raise HTTPException(
            400,
            "Username must be 3-32 characters (letters, digits, underscore or dot).",
        )
    if database.query_one("SELECT id FROM users WHERE username = ?", (username,)):
        raise HTTPException(400, f"Username '{username}' is already taken.")
    user_id = database.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')",
        (username, hash_password(payload.password)),
    )
    user = database.query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    log.info("New user registered: %s", username)
    return TokenResponse(access_token=create_access_token(user), username=user["username"], role=user["role"])


@router.post("/login", response_model=TokenResponse, summary="Log in and receive a JWT token")
def login(payload: LoginRequest):
    user = database.query_one("SELECT * FROM users WHERE username = ?", (payload.username.strip(),))
    if user is None or not verify_password(payload.password, user["password_hash"]):
        log.warning("Failed login attempt for username=%r", payload.username)
        raise HTTPException(401, "Incorrect username or password.")
    log.info("User logged in: %s", user["username"])
    return TokenResponse(access_token=create_access_token(user), username=user["username"], role=user["role"])


@router.get("/me", summary="Get the currently logged-in user")
def me(user: dict = Depends(get_current_user)):
    return _public_user(user)


@router.get("/users", summary="List users (admin only)", dependencies=[])
def list_users(admin: dict = Depends(get_current_user)):
    if admin["role"] != "admin":
        raise HTTPException(403, "Admin privileges required.")
    return [_public_user(u) for u in database.query("SELECT * FROM users ORDER BY id")]
