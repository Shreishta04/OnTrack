"""Sending one alert to one phone, through Firebase Cloud Messaging (FCM).

Firebase is only the post office: OnTrack decides what to say and when
(notify.py), Firebase delivers it to Apple's or Google's push service, which
wakes the phone.

Setup (once): Firebase console → Project settings → Service accounts →
Generate new private key. Paste the WHOLE file into the Railway variable
FIREBASE_SERVICE_ACCOUNT. It's a password for your Firebase project: never in
git, never in a chat.

The message is "data only": the app's service worker (frontend/public/sw.js)
turns it into the notification, so it looks the same on every phone.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading

log = logging.getLogger("uvicorn.error")

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_session = None
_lock = threading.Lock()


def _account() -> dict | None:
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except ValueError:
        log.warning("push     FIREBASE_SERVICE_ACCOUNT isn't valid JSON: paste the whole downloaded file")
        return None
    return info if info.get("type") == "service_account" and info.get("project_id") else None


def configured() -> bool:
    return _account() is not None


def web_setup() -> dict | None:
    """What the app needs to ask Firebase for this phone's token. Not secret
    (it's in every Firebase web app's code), but kept in Railway variables so
    a new Firebase project needs no code change:

        FIREBASE_WEB_CONFIG   the firebaseConfig block from Project settings →
                              Your apps (pasted as it is, JavaScript or JSON)
        FIREBASE_VAPID_KEY    Cloud Messaging → Web Push certificates → Key pair
    """
    raw = os.getenv("FIREBASE_WEB_CONFIG", "")
    vapid = os.getenv("FIREBASE_VAPID_KEY", "").strip()
    # key: "value" pairs, whether written as JSON or as the JavaScript Firebase shows
    config = dict(re.findall(r'["\']?(\w+)["\']?\s*:\s*["\']([^"\']+)["\']', raw))
    needed = ("apiKey", "projectId", "messagingSenderId", "appId")
    if not vapid or not all(config.get(k) for k in needed):
        return None
    return {"config": {k: config[k] for k in (*needed, "authDomain", "storageBucket") if k in config},
            "vapid_key": vapid}


def _authorized():
    """A web session that adds Google's short-lived access token to each request
    (and renews it every hour). Loaded only when an alert is actually sent."""
    global _session
    with _lock:
        if _session is None:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_info(_account(), scopes=[SCOPE])
            _session = AuthorizedSession(creds)
        return _session


def send(token: str, message: dict) -> str:
    """'ok', 'gone' (this phone no longer takes alerts: forget it) or 'error'."""
    account = _account()
    if not account:
        return "error"
    body = {"message": {
        "token": token,
        "data": {k: str(v) for k, v in message.items() if v is not None},   # data values must be text
        "webpush": {"headers": {"Urgency": "high", "TTL": "86400"}},
    }}
    url = f"https://fcm.googleapis.com/v1/projects/{account['project_id']}/messages:send"
    try:
        r = _authorized().post(url, json=body, timeout=15)
    except Exception as exc:
        log.warning("push     failed: %s", type(exc).__name__)
        return "error"
    if r.status_code == 200:
        return "ok"
    text = r.text[:300]
    if r.status_code == 404 or "UNREGISTERED" in text or "SENDER_ID_MISMATCH" in text:
        return "gone"
    if r.status_code == 400 and "registration token" in text.lower():
        return "gone"
    log.warning("push     FCM answered %s: %s", r.status_code, text)
    return "error"
