"""Short sentences for the iPhone Shortcuts, instead of JSON.

A Shortcut that adds `?reply=text` to its address gets one line it can show as
a notification ("Added to OnTrack · Coach Tabby Bag · $450"). Without it,
everything answers JSON exactly as before, so old Shortcuts keep working.

The wording lives here, on the server, so it can be improved without anyone
editing the Shortcut on their phone again.
"""

from __future__ import annotations

NAME_MAX = 60     # a notification shows about two lines

SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AED": "AED ", "SGD": "S$",
           "CAD": "C$", "AUD": "A$", "JPY": "¥"}


def wants_text(query: dict) -> bool:
    return query.get("reply") == "text"


def money(amount: float | None, currency: str = "INR") -> str:
    """₹1,24,999 / $1,249.50: Indian grouping for rupees, plain thousands otherwise,
    and no ".00" on whole amounts."""
    if amount is None:
        return "no price"
    symbol = SYMBOLS.get(currency, currency + " ")
    whole = round(amount, 2) == int(amount)
    if currency == "INR":
        rupees = int(round(amount)) if whole else int(amount)
        digits = str(abs(rupees))
        if len(digits) > 3:          # 1,24,999: the last three, then pairs
            head, tail = digits[:-3], digits[-3:]
            pairs = []
            while len(head) > 2:
                pairs.insert(0, head[-2:])
                head = head[:-2]
            digits = ",".join([head, *pairs, tail])
        paise = "" if whole else f"{amount - int(amount):.2f}"[1:]
        return f"{symbol}{digits}{paise}"
    return f"{symbol}{amount:,.0f}" if whole else f"{symbol}{amount:,.2f}"


def short(name: str | None) -> str:
    name = " ".join((name or "").split())
    if not name or name.startswith("http"):
        return "your item"
    return name if len(name) <= NAME_MAX else name[: NAME_MAX - 1].rstrip() + "…"


def item_added(item: dict, currency: str) -> str:
    if item["price"] is not None:
        return f"Added to OnTrack · {short(item['name'])} · {money(item['price'], currency)}"
    return (f"Added, but no price yet · {short(item['name'])}. "
            "Open OnTrack to type one.")


def duplicate(name: str | None) -> str:
    return f"Already on your list · {short(name)}"


def link_checked(name: str | None, result: dict, currency: str) -> str:
    """One line per item for the Refresh Shortcut (it shows them all together)."""
    if not result["ok"]:
        return f"{short(name)}: couldn't read the price this time"
    old, new = result["old_price"], result["new_price"]
    if old is None or old == new:
        return f"{short(name)}: {money(new, currency)}"
    arrow = "↓" if new < old else "↑"
    return f"{short(name)}: {arrow} {money(new, currency)} (was {money(old, currency)})"


def error(status: int, detail: str | None) -> str:
    """Errors, in words someone holding a phone can act on."""
    if status == 401:
        return ("OnTrack doesn't recognise this Shortcut's key. Make a new one in "
                "Settings → Shortcuts and extension, and paste it into the Shortcut.")
    if status == 400 and detail and "multipart" in detail.lower():
        return ("The page didn't upload properly. Try again, or copy the link and run "
                "Add to OnTrack from your Home Screen.")
    if status == 422:
        return "OnTrack couldn't read that link. Share the product page itself, or copy its link."
    if status == 404:
        return "That item isn't on your list any more."
    if status == 429:
        return "Too many at once. Wait a minute, then try again."
    if status >= 500:
        return "Something went wrong on OnTrack's side. Try again in a moment."
    return detail or f"OnTrack answered with error {status}."
