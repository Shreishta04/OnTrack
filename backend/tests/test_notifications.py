"""Notifications: which alerts are made, when they're held, and who gets them.

Firebase is replaced by a fake post box (`sent`), so no real phone buzzes.
The clock is set by hand (services._utcnow). Times are UTC; India is 5.5
hours ahead, so 04:00 UTC is 9:30 am there and 18:00 UTC is 11:30 pm.
"""

from datetime import datetime

import pytest

import main
import services
from extractor import OUT_OF_STOCK, Product
from test_api import H, client  # noqa: F401  (client is a pytest fixture)

PHONE = "phone-token-" + "x" * 30
SECRET = {"X-Cron-Secret": "cron-secret-long-enough-1234567"}
FASTRACK = "https://www.fastrack.in/ryz.html"


def at(monkeypatch, stamp):
    monkeypatch.setattr(services, "_utcnow", lambda: datetime.fromisoformat(stamp))


class PostBox(list):
    """Stands in for Firebase: every alert "sent" is added to this list, as
    (phone token, message). Tokens in .gone act like a phone whose app was deleted."""
    def __init__(self):
        super().__init__()
        self.gone = set()

    def send(self, token, message):
        if token in self.gone:
            return "gone"
        self.append((token, message))
        return "ok"

    def bodies(self):
        return [message["body"] for _, message in self]


@pytest.fixture
def sent(client, monkeypatch):
    box = PostBox()
    main.app.dependency_overrides[main.get_sender] = lambda: box.send
    monkeypatch.setenv("ONTRACK_CRON_SECRET", SECRET["X-Cron-Secret"])
    return box


def phone_on(c, token=PHONE):
    assert c.post("/push/devices", json={"token": token, "platform": "iphone"}, headers=H).status_code == 204


def add_watch(c):
    return c.post("/items/from-link", json={"url": FASTRACK}, headers=H).json()


def store_price(c, price=None, error=None):
    c.catalogue[FASTRACK] = Product(url=FASTRACK, ok=price is not None, title="Fastrack Ryz Women Smartwatch",
                                    price=price, error=error, method="json-ld")


# ------------------------------------------------------------------ settings

def test_all_four_are_on_until_switched_off(client, sent):
    r = client.get("/notifications", headers=H).json()
    assert r["settings"] == {"price_drop": True, "budget_reset": True, "waiting": True, "back_in_stock": True}
    assert r["devices"] == 0
    r = client.put("/notifications", json={"waiting": False}, headers=H).json()
    assert r["settings"]["waiting"] is False and r["settings"]["price_drop"] is True   # only that one changed
    assert client.get("/notifications", headers=H).json()["settings"]["waiting"] is False
    assert client.get("/notifications").status_code == 401


def test_a_phone_is_remembered_once_and_can_be_removed(client, sent):
    phone_on(client)
    phone_on(client)                                          # tapping again doesn't add it twice
    assert client.get("/notifications", headers=H).json()["devices"] == 1
    client.post("/push/devices/remove", json={"token": PHONE}, headers=H)
    assert client.get("/notifications", headers=H).json()["devices"] == 0


# --------------------------------------------------------------- price alerts

def test_a_price_drop_is_sent_once(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-12T06:00:00+00:00")             # 11:30 am in India
    phone_on(client)
    add_watch(client)                                         # ₹2,499: a new item is not news
    assert len(sent) == 0
    store_price(client, 1899)
    client.post("/refresh?force=true", headers=H)
    assert sent.bodies() == ["Fastrack Ryz Women Smartwatch: ↓ ₹1,899 (was ₹2,499)"]
    assert sent[0][1]["title"] == "Price dropped" and sent[0][1]["url"] == "/"
    client.post("/refresh?force=true", headers=H)             # same price again: nothing new
    store_price(client, 2199)
    client.post("/refresh?force=true", headers=H)             # it went UP: no alert
    assert len(sent) == 1


def test_back_in_stock(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-12T06:00:00+00:00")
    phone_on(client)
    add_watch(client)
    store_price(client, error=OUT_OF_STOCK)
    client.post("/refresh?force=true", headers=H)
    store_price(client, 2499)
    client.post("/refresh?force=true", headers=H)
    assert sent.bodies() == ["Fastrack Ryz Women Smartwatch is back: ₹2,499"]


def test_switched_off_means_no_alert(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-12T06:00:00+00:00")
    phone_on(client)
    client.put("/notifications", json={"price_drop": False}, headers=H)
    add_watch(client)
    store_price(client, 1899)
    client.post("/refresh?force=true", headers=H)
    assert len(sent) == 0


def test_no_phone_means_nothing_piles_up(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-12T06:00:00+00:00")
    add_watch(client)
    store_price(client, 1899)
    client.post("/refresh?force=true", headers=H)
    phone_on(client)                                          # alerts turned on later
    client.post("/cron/tick", headers=SECRET)
    assert len(sent) == 0                                     # yesterday's news isn't sent


def test_bought_items_send_nothing(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-12T06:00:00+00:00")
    phone_on(client)
    item = add_watch(client)
    client.patch(f"/items/{item['id']}", json={"status": "purchased"}, headers=H)
    store_price(client, 1899)
    client.post("/refresh?force=true", headers=H)
    assert len(sent) == 0


# ---------------------------------------------------------------- quiet hours

def test_alerts_found_at_night_wait_for_morning(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-12T18:00:00+00:00")             # 11:30 pm in India
    phone_on(client)
    add_watch(client)
    store_price(client, 1899)
    client.post("/refresh?force=true", headers=H)
    assert len(sent) == 0                                     # held
    at(monkeypatch, "2026-11-13T01:30:00+00:00")             # 7 am: still quiet
    client.post("/cron/tick", headers=SECRET)
    assert len(sent) == 0
    at(monkeypatch, "2026-11-13T02:30:00+00:00")             # 8 am
    client.post("/cron/tick", headers=SECRET)
    assert sent.bodies() == ["Fastrack Ryz Women Smartwatch: ↓ ₹1,899 (was ₹2,499)"]


def test_the_test_button_ignores_quiet_hours(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-12T18:00:00+00:00")
    assert client.post("/push/test", headers=H).json()["devices"] == 0     # no phone yet: says so
    phone_on(client)
    r = client.post("/push/test", headers=H).json()
    assert r["sent"] == 1 and sent[0][1]["title"] == "OnTrack alerts are on"


def test_a_deleted_app_is_forgotten(client, sent):
    phone_on(client)
    sent.gone.add(PHONE)
    client.post("/push/test", headers=H)
    assert client.get("/notifications", headers=H).json()["devices"] == 0


def test_many_at_once_become_one(client, sent, monkeypatch):
    import db
    import notify
    at(monkeypatch, "2026-11-12T06:00:00+00:00")
    phone_on(client)
    conn = db.connect()
    uid = conn.execute("SELECT id FROM users").fetchone()["id"]
    for n in range(5):
        notify.queue(conn, uid, "price_drop", "Price dropped", f"Thing {n}: ↓ ₹1", f"k{n}")
    conn.commit()
    notify.flush(conn, uid, sent.send)
    conn.close()
    assert len(sent) == 1 and sent[0][1]["title"] == "5 updates from OnTrack"
    assert sent[0][1]["body"].endswith("…and 2 more")


# --------------------------------------------------------------- daily round

def test_the_daily_round_checks_prices_at_9_am(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-12T02:00:00+00:00")             # 7:30 am in India
    phone_on(client)
    add_watch(client)
    store_price(client, 1899)
    assert client.post("/cron/tick", headers=SECRET).json()["daily_rounds"] == 0   # too early
    monkeypatch.setattr(services, "_is_due", lambda last, force: True)              # (skip the 1-hour cooldown)
    at(monkeypatch, "2026-11-12T04:00:00+00:00")             # 9:30 am
    assert client.post("/cron/tick", headers=SECRET).json()["daily_rounds"] == 1
    assert sent.bodies() == ["Fastrack Ryz Women Smartwatch: ↓ ₹1,899 (was ₹2,499)"]
    at(monkeypatch, "2026-11-12T05:00:00+00:00")
    assert client.post("/cron/tick", headers=SECRET).json()["daily_rounds"] == 0   # once a day


def test_budget_reset_reminder_on_the_last_day(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-23T04:00:00+00:00")             # 24 Nov is the period's last day
    client.put("/budget", json={"amount": 15000, "reset_day": 25}, headers=H)
    phone_on(client)
    client.post("/cron/tick", headers=SECRET)
    assert len(sent) == 0                                     # not the last day yet
    at(monkeypatch, "2026-11-24T04:00:00+00:00")
    client.post("/cron/tick", headers=SECRET)
    assert sent.bodies() == ["Your budget starts again tomorrow: ₹15,000."]


def test_waiting_reminder_on_mondays(client, sent, monkeypatch):
    at(monkeypatch, "2026-11-01T06:00:00+00:00")
    phone_on(client)
    client.post("/items", json={"name": "Linen Shirt", "price": 1299}, headers=H)
    at(monkeypatch, "2026-11-12T04:00:00+00:00")             # a Thursday
    client.post("/cron/tick", headers=SECRET)
    at(monkeypatch, "2026-11-16T04:00:00+00:00")             # Monday, 15 days later
    client.post("/cron/tick", headers=SECRET)
    assert sent.bodies() == ["Linen Shirt has been on your list for 2+ weeks."]


def test_cron_needs_the_secret(client, sent, monkeypatch):
    assert client.post("/cron/tick").status_code == 401
    assert client.post("/cron/tick", headers={"X-Cron-Secret": "wrong"}).status_code == 401
    monkeypatch.setenv("ONTRACK_CRON_SECRET", "short")
    assert client.post("/cron/tick", headers={"X-Cron-Secret": "short"}).status_code == 503   # too easy to guess


# ------------------------------------------------------------- Firebase (fcm.py)

ACCOUNT = '{"type": "service_account", "project_id": "ontrack-test", "client_email": "x@y"}'


class FakeAnswer:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


def test_firebase_setup_is_checked(monkeypatch):
    import fcm
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT", raising=False)
    assert not fcm.configured()
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT", "{half a file")
    assert not fcm.configured()                               # pasted badly: not "on"
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT", ACCOUNT)
    assert fcm.configured()


def test_firebase_answers_become_ok_gone_or_error(monkeypatch):
    import fcm
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT", ACCOUNT)
    posted = []

    class Session:
        answer = FakeAnswer(200)

        def post(self, url, json, timeout):
            posted.append((url, json))
            return self.answer

    session = Session()
    monkeypatch.setattr(fcm, "_authorized", lambda: session)
    assert fcm.send(PHONE, {"title": "Price dropped", "body": "Kurta", "item": 7}) == "ok"
    url, body = posted[0]
    assert url == "https://fcm.googleapis.com/v1/projects/ontrack-test/messages:send"
    assert body["message"]["data"] == {"title": "Price dropped", "body": "Kurta", "item": "7"}   # all text
    session.answer = FakeAnswer(404, '{"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}}')
    assert fcm.send(PHONE, {"title": "t"}) == "gone"
    session.answer = FakeAnswer(500, "oops")
    assert fcm.send(PHONE, {"title": "t"}) == "error"


def test_web_setup_reads_firebases_own_snippet(monkeypatch):
    import fcm
    monkeypatch.setenv("FIREBASE_WEB_CONFIG", """const firebaseConfig = {
  apiKey: "AIzaSyExample",
  authDomain: "ontrack-test.firebaseapp.com",
  projectId: "ontrack-test",
  storageBucket: "ontrack-test.firebasestorage.app",
  messagingSenderId: "1234567890",
  appId: "1:1234567890:web:abc123"
};""")
    monkeypatch.delenv("FIREBASE_VAPID_KEY", raising=False)
    assert fcm.web_setup() is None                            # half set up: not offered
    monkeypatch.setenv("FIREBASE_VAPID_KEY", "BExampleVapidKey")
    web = fcm.web_setup()
    assert web["vapid_key"] == "BExampleVapidKey"
    assert web["config"]["appId"] == "1:1234567890:web:abc123" and web["config"]["projectId"] == "ontrack-test"
