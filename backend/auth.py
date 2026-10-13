"""
Accounts: sign-up by invite, log in, tokens, password resets.

How a request proves who it is
------------------------------
Every request sends a token in the X-API-Key header, exactly like the old
shared key, so the Shortcuts and the extension keep working unchanged: they
just get their own token. There are two kinds:

  session  made when you log in on the web app; removed when you log out
  device   made in Settings for a Shortcut or the extension; revoke it there
           if a phone is lost, without touching anything else

Why a header and not a cookie: the web app (Vercel) and the server (Railway)
are on different sites, and Safari blocks cookies sent between different
sites. A header always works.

Only a SHA-256 hash of each token is stored. Tokens are 32 random bytes, so
a fast hash is enough: nobody can guess one. Passwords are different (people
choose short, guessable ones), so they get scrypt, a hash that is slow and
memory-hungry on purpose, which makes guessing millions of them expensive.

The owner key
-------------
ONTRACK_API_KEY still works, and acts as the owner (the first account). It
is also the invite code for creating that first account, so nobody else can
grab it after a deploy. Once every Shortcut has its own device token, the
owner key can be retired.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import services


class AuthError(Exception):
    """Something about who you are is wrong: answered with 401."""


class Forbidden(Exception):
    """You're logged in but this isn't yours to do: answered with 403."""


class BadRequest(Exception):
    """The request can't be done as asked (taken email, used invite): 400."""


# ------------------------------------------------------------- passwords
# scrypt settings: n=2**15, r=8 uses 32 MB and about 0.1 s per check. Stored
# with the hash, so they can be raised later without breaking old passwords.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1
PASSWORD_MIN, PASSWORD_MAX = 10, 200          # MAX: hashing a megabyte "password" wastes CPU


def hash_password(password: str) -> str:
    salt = os.urandom(16)                     # different for every password: same passwords, different hashes
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                            maxmem=64 * 1024 * 1024, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r),
                                p=int(p), maxmem=64 * 1024 * 1024, dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)   # same time whether 1 or 31 bytes match


# A hash of a random password, checked when the email doesn't exist, so a
# wrong email takes as long as a wrong password. Otherwise the answer's speed
# would tell a stranger which emails have accounts.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# ---------------------------------------------------------------- tokens

def new_secret() -> str:
    return secrets.token_urlsafe(32)          # 256 random bits


def secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _make_token(conn, user_id: int, kind: str, name: str) -> str:
    """Create a token and return it. This is the only time it exists in full."""
    secret = new_secret()
    conn.execute("INSERT INTO tokens (user_id, token_hash, kind, name, created_at) VALUES (?, ?, ?, ?, ?)",
                 (user_id, secret_hash(secret), kind, name, services.now()))
    return secret


LAST_USED_EVERY = timedelta(hours=1)   # note "last used" at most once an hour: not a write per request


def user_for_token(conn, secret: str | None) -> dict:
    """The user this token belongs to, or AuthError."""
    if not secret:
        raise AuthError("Log in first.")
    owner_key = os.environ.get("ONTRACK_API_KEY", "")
    if owner_key and hmac.compare_digest(secret, owner_key):
        row = conn.execute("SELECT * FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1").fetchone()
        if not row:
            raise AuthError("Create your account first: open the app and use this key as the invite code.")
        return dict(row) | {"token_id": None}

    row = conn.execute("SELECT users.*, tokens.id AS token_id, tokens.last_used_at FROM tokens "
                       "JOIN users ON users.id = tokens.user_id WHERE tokens.token_hash = ?",
                       (secret_hash(secret),)).fetchone()
    if not row:
        raise AuthError("This key or login isn't valid any more. Log in again.")
    user = dict(row)
    stale = (services._utcnow() - LAST_USED_EVERY).isoformat(timespec="seconds")
    if not user["last_used_at"] or user["last_used_at"] < stale:
        conn.execute("UPDATE tokens SET last_used_at = ? WHERE id = ?", (services.now(), user["token_id"]))
        conn.commit()
    return user


def public_user(user: dict) -> dict:
    """What the app may see about a user: never the password hash."""
    return {k: user[k] for k in ("id", "email", "name", "currency", "country", "timezone", "created_at")} \
        | {"is_admin": bool(user["is_admin"])}


# ------------------------------------------------------------ validation
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CURRENCIES = ("INR", "USD", "EUR", "GBP", "AED", "SGD", "CAD", "AUD", "JPY")


def clean_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > 254 or not EMAIL.match(email):
        raise BadRequest("That doesn't look like an email address.")
    return email


def check_password(password: str) -> None:
    if len(password) < PASSWORD_MIN:
        raise BadRequest(f"Use at least {PASSWORD_MIN} characters for the password.")
    if len(password) > PASSWORD_MAX:
        raise BadRequest(f"Use at most {PASSWORD_MAX} characters for the password.")


def check_place(currency: str, country: str, tz: str) -> None:
    if currency not in CURRENCIES:
        raise BadRequest(f"OnTrack doesn't support the currency {currency!r} yet.")
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise BadRequest("Country should be a two-letter code, like IN or US.")
    try:
        ZoneInfo(tz)
    except Exception:
        raise BadRequest(f"{tz!r} isn't a time zone name (like Asia/Kolkata).") from None


# --------------------------------------------------------------- invites
INVITE_DAYS = 7
RESET_DAYS = 2


def _open_invite(conn, code: str):
    """The unused, unexpired invite with this code, or BadRequest."""
    row = conn.execute("SELECT * FROM invites WHERE code_hash = ?", (secret_hash(code.strip()),)).fetchone()
    if not row or row["used_at"] or row["expires_at"] < services.now():
        raise BadRequest("This invite link has expired or was already used. Ask for a new one.")
    return row


def create_invite(conn, admin: dict, note: str | None = None, for_user_id: int | None = None) -> dict:
    if not admin["is_admin"]:
        raise Forbidden("Only the owner can invite people.")
    if for_user_id is not None and not conn.execute("SELECT 1 FROM users WHERE id = ?", (for_user_id,)).fetchone():
        raise services.NotFound(f"user {for_user_id}")
    code = new_secret()
    days = RESET_DAYS if for_user_id else INVITE_DAYS
    expires = (services._utcnow() + timedelta(days=days)).isoformat(timespec="seconds")
    invite_id = conn.execute(
        "INSERT INTO invites (code_hash, created_by, for_user_id, note, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        (secret_hash(code), admin["id"], for_user_id, note, services.now(), expires)).fetchone()["id"]
    conn.commit()
    return {"id": invite_id, "code": code, "expires_at": expires}


def list_invites(conn, admin: dict) -> list[dict]:
    if not admin["is_admin"]:
        raise Forbidden("Only the owner can see invites.")
    rows = conn.execute(
        "SELECT invites.id, invites.note, invites.created_at, invites.expires_at, invites.used_at, "
        "users.email AS for_email FROM invites LEFT JOIN users ON users.id = invites.for_user_id "
        "ORDER BY invites.id DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]


def delete_invite(conn, admin: dict, invite_id: int) -> None:
    if not admin["is_admin"]:
        raise Forbidden("Only the owner can cancel invites.")
    if conn.execute("DELETE FROM invites WHERE id = ?", (invite_id,)).rowcount == 0:
        raise services.NotFound(f"invite {invite_id}")
    conn.commit()


def list_users(conn, admin: dict) -> list[dict]:
    if not admin["is_admin"]:
        raise Forbidden("Only the owner can see everyone.")
    rows = conn.execute(
        "SELECT users.id, users.email, users.name, users.is_admin, users.created_at, "
        "(SELECT COUNT(*) FROM items WHERE items.user_id = users.id) AS items "
        "FROM users ORDER BY users.id").fetchall()
    return [dict(r) | {"is_admin": bool(r["is_admin"])} for r in rows]


# ------------------------------------------------- sign up, log in, reset

def signup(conn, invite: str, email: str, password: str, name: str,
           currency: str, country: str, tz: str) -> tuple[dict, str]:
    """Create an account with an invite code. Returns (user, session token).

    The very first account uses ONTRACK_API_KEY as its invite. It becomes the
    owner and is given everything already in the database (the list from
    before Accounts) and the old budget."""
    email = clean_email(email)
    check_password(password)
    check_place(currency, country, tz)
    name = name.strip() or email.split("@")[0]

    first = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
    if first:
        owner_key = os.environ.get("ONTRACK_API_KEY", "")
        if not (owner_key and hmac.compare_digest(invite.strip(), owner_key)):
            raise BadRequest("For the first account, the invite code is the server's ONTRACK_API_KEY.")
        invite_row = None
    else:
        invite_row = _open_invite(conn, invite)
        if invite_row["for_user_id"]:
            raise BadRequest("That's a password-reset link, not an invite.")
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise BadRequest("There's already an account with this email. Log in instead.")

    user_id = conn.execute(
        "INSERT INTO users (email, name, password_hash, is_admin, currency, country, timezone, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (email, name, hash_password(password), 1 if first else 0, currency, country, tz,
         services.now())).fetchone()["id"]
    if first:
        _give_old_list_to(conn, user_id)
    else:
        conn.execute("UPDATE invites SET used_at = ? WHERE id = ?", (services.now(), invite_row["id"]))
    token = _make_token(conn, user_id, "session", "Web app")
    conn.commit()
    return _user(conn, user_id), token


def _give_old_list_to(conn, user_id: int) -> None:
    """Everything saved before Accounts belongs to the owner."""
    conn.execute("UPDATE items SET user_id = ? WHERE user_id IS NULL", (user_id,))
    conn.execute("UPDATE links SET user_id = (SELECT items.user_id FROM items WHERE items.id = links.item_id) "
                 "WHERE user_id IS NULL")
    old = conn.execute("SELECT value FROM settings WHERE key = 'budget'").fetchone()
    if old:
        conn.execute("UPDATE users SET budget = ? WHERE id = ?", (float(old["value"]), user_id))


def login(conn, email: str, password: str) -> tuple[dict, str]:
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    ok = verify_password(password[:PASSWORD_MAX], row["password_hash"] if row else _DUMMY_HASH)
    if not (row and ok):
        raise AuthError("Email or password is wrong.")   # never say which: that would confirm the email
    token = _make_token(conn, row["id"], "session", "Web app")
    conn.commit()
    return _user(conn, row["id"]), token


def reset_password(conn, code: str, password: str) -> tuple[dict, str]:
    """Use a reset link: new password, every old login signed out (device
    tokens are kept, so the Shortcuts don't break)."""
    check_password(password)
    invite = _open_invite(conn, code)
    if not invite["for_user_id"]:
        raise BadRequest("That's an invite link, not a password reset. Use it to sign up.")
    user_id = invite["for_user_id"]
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
    conn.execute("UPDATE invites SET used_at = ? WHERE id = ?", (services.now(), invite["id"]))
    conn.execute("DELETE FROM tokens WHERE user_id = ? AND kind = 'session'", (user_id,))
    token = _make_token(conn, user_id, "session", "Web app")
    conn.commit()
    return _user(conn, user_id), token


def change_password(conn, user: dict, current: str, new: str) -> None:
    if not verify_password(current[:PASSWORD_MAX], user["password_hash"]):
        raise BadRequest("The current password is wrong.")
    check_password(new)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user["id"]))
    # Sign out every OTHER login (someone else may know the old password).
    conn.execute("DELETE FROM tokens WHERE user_id = ? AND kind = 'session' AND id != ?",
                 (user["id"], user["token_id"] or 0))
    conn.commit()


def logout(conn, user: dict) -> None:
    if user["token_id"]:
        conn.execute("DELETE FROM tokens WHERE id = ?", (user["token_id"],))
        conn.commit()


def _user(conn, user_id: int) -> dict:
    return public_user(dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()))


def update_profile(conn, user: dict, **fields) -> dict:
    changes = {k: v for k, v in fields.items() if v is not None and k in ("name", "currency", "country", "timezone")}
    merged = {"currency": user["currency"], "country": user["country"], "timezone": user["timezone"]} | changes
    check_place(merged["currency"], merged["country"], merged["timezone"])
    if "name" in changes:
        changes["name"] = changes["name"].strip() or user["name"]
    if changes:
        sets = ", ".join(f"{k} = ?" for k in changes)
        conn.execute(f"UPDATE users SET {sets} WHERE id = ?", (*changes.values(), user["id"]))
        conn.commit()
    return _user(conn, user["id"])


# ---------------------------------------------------------- device tokens

def list_tokens(conn, user: dict) -> list[dict]:
    rows = conn.execute("SELECT id, kind, name, created_at, last_used_at FROM tokens "
                        "WHERE user_id = ? ORDER BY id", (user["id"],)).fetchall()
    return [dict(r) | {"current": r["id"] == user["token_id"]} for r in rows]


def create_device_token(conn, user: dict, name: str) -> dict:
    name = name.strip()[:60] or "Device"
    secret = _make_token(conn, user["id"], "device", name)
    conn.commit()
    return {"name": name, "token": secret}


def revoke_token(conn, user: dict, token_id: int) -> None:
    if conn.execute("DELETE FROM tokens WHERE id = ? AND user_id = ?", (token_id, user["id"])).rowcount == 0:
        raise services.NotFound(f"token {token_id}")
    conn.commit()
