"""
FastAPI app: turns HTTP requests into calls to services.py.

Run locally:
    uvicorn main:app --reload
Then open http://127.0.0.1:8000/docs to try every endpoint in the browser.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

import socket

import db
import services
from extractor import UnsafeURL, check_public_url
from services import Duplicate, NotFound
from typing import Literal
load_dotenv()   # reads settings from .env (kept out of git) into environment variables


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("ONTRACK_API_KEY"):
        raise RuntimeError("ONTRACK_API_KEY is not set. Copy .env.example to .env and set it.")
    conn = db.connect()
    db.init(conn)        # create tables on first run
    conn.close()
    yield


app = FastAPI(title="OnTrack API", version="0.1.0", lifespan=lifespan)


# Upload size limit. The phone and the extension upload whole store pages
# (an Amazon page is about 1.7 MB). Without a limit, one huge upload could fill
# the server's memory or disk. The check runs BEFORE anything else reads the
# request, even before the API key is checked, so an outsider can't send one
# either. ONTRACK_MAX_UPLOAD_MB changes the limit.
MAX_UPLOAD_MB = float(os.getenv("ONTRACK_MAX_UPLOAD_MB", "5"))


class LimitRequestSize:
    """Refuse requests bigger than max_bytes with 413 "Payload Too Large".

    Two checks: the Content-Length header (the size the sender announces),
    and a running count of the bytes that actually arrive, for senders that
    don't announce a size or announce the wrong one. When the count goes over,
    we answer 413 ourselves and tell the app the sender has gone away, so it
    stops reading (raising an error instead would be caught by FastAPI and
    turned into a confusing 400)."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        announced = dict(scope["headers"]).get(b"content-length", b"")
        if announced.isdigit() and int(announced) > self.max_bytes:
            return await self.too_large(send)

        received, answered = 0, False

        async def counting_receive():
            nonlocal received, answered
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    if not answered:
                        answered = True
                        await self.too_large(send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            if not answered:                 # once we've said 413, the app's own answer is dropped
                await send(message)

        await self.app(scope, counting_receive, guarded_send)

    async def too_large(self, send):
        response = JSONResponse(status_code=413, content={
            "detail": f"That's too big to upload (the limit is {MAX_UPLOAD_MB:g} MB)."})
        await response({"type": "http"}, None, send)


# The form wrapped around a page adds a few hundred bytes; 64 KB is plenty.
app.add_middleware(LimitRequestSize, max_bytes=int(MAX_UPLOAD_MB * 1024 * 1024) + 64 * 1024)


# Rate limiting: at most N requests a minute from one address. A leaked key, a
# Shortcut stuck in a loop or someone hammering the server can't burn through
# the hosting credit or get my server blocked by the stores. "Heavy" requests
# make the server download store pages, so they get a much lower limit.
RATE_LIMIT = int(os.getenv("ONTRACK_RATE_LIMIT", "60"))              # per minute, any request
RATE_LIMIT_HEAVY = int(os.getenv("ONTRACK_RATE_LIMIT_HEAVY", "10"))  # per minute, page downloads
HEAVY_REQUESTS = re.compile(r"^POST (/items/from-link|/items/from-html|/items/\d+/links"
                            r"|/refresh|/items/\d+/refresh)$")


class RateLimiter:
    """Remembers when each address made its recent requests ("sliding window":
    always the last 60 seconds, not "this calendar minute", so a burst can't
    straddle two minutes to get double).

    Kept in memory: fine for one server process. If OnTrack ever runs on several
    servers at once, this would need a shared store such as Redis."""

    def __init__(self, clock=time.monotonic, window: float = 60.0):
        self.clock, self.window = clock, window
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)

    def allow(self, key: str, bucket: str, limit: int) -> float:
        """0 if the request may go ahead, else seconds until it would be allowed."""
        now = self.clock()
        hits = self.hits[(key, bucket)]
        while hits and hits[0] <= now - self.window:      # forget requests older than the window
            hits.popleft()
        if len(hits) >= limit:
            return hits[0] + self.window - now
        hits.append(now)
        if len(self.hits) > 10_000:                       # don't let many addresses fill the memory
            self.hits = defaultdict(deque, {k: v for k, v in self.hits.items() if v})
        return 0.0

    def reset(self) -> None:
        self.hits.clear()


rate_limiter = RateLimiter()


class LimitRequestRate:
    """Answers 429 "Too Many Requests" (with Retry-After: seconds to wait) once
    an address goes over the limit. Runs before the upload is read and before
    the API key is checked, so refused requests cost almost nothing."""

    def __init__(self, app, limiter: RateLimiter):
        self.app, self.limiter = app, limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health" or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        # On Railway, the real address comes from the proxy in front of the server:
        # uvicorn must be started with --proxy-headers (see README, Deploy).
        who = (scope.get("client") or ("unknown", 0))[0]
        wait = self.limiter.allow(who, "all", RATE_LIMIT)
        if not wait and HEAVY_REQUESTS.match(f"{scope['method']} {scope['path']}"):
            wait = self.limiter.allow(who, "heavy", RATE_LIMIT_HEAVY)
        if wait:
            response = JSONResponse(
                status_code=429, headers={"Retry-After": str(int(wait) + 1)},
                content={"detail": f"Too many requests. Try again in {int(wait) + 1} s."})
            return await response(scope, receive, send)
        await self.app(scope, receive, send)


app.add_middleware(LimitRequestRate, limiter=rate_limiter)

# CORS: browsers block a web page from calling an API on a different origin
# (different host or port) unless the API explicitly allows it. The React app
# will run on localhost:5173 during development, so allow that.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ONTRACK_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uvicorn prints a request's line only when it FINISHES. A request that gets
# stuck never shows up, so the terminal looks silent. Printing when each request
# STARTS (and how long slow ones took) makes a stuck request easy to spot.
log = logging.getLogger("uvicorn.error")   # the logger uvicorn already prints to
SLOW_REQUEST_SECONDS = 2


@app.middleware("http")
async def log_request_start(request: Request, call_next):
    start = time.monotonic()
    log.info("started  %s %s", request.method, request.url.path)
    response = await call_next(request)
    took = time.monotonic() - start
    if took >= SLOW_REQUEST_SECONDS:
        log.info("slow     %s %s took %.1f s", request.method, request.url.path, took)
    return response


# --------------------------------------------------------------- dependencies

def get_db():
    """One database connection per request, always closed afterwards."""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def get_extract():
    """Which extractor to use. Tests override this with a fake."""
    return services.default_extract


def get_resolver():
    """How website names are looked up. Tests override this, so they never use the network."""
    return socket.getaddrinfo


def refuse_unsafe(url: str, resolve) -> None:
    """Answer 400 for a link to a private or internal address, instead of saving
    an item that can never be fetched. (The download itself checks again,
    including every redirect: this is only the friendly early answer.)"""
    try:
        check_public_url(url, resolve)
    except UnsafeURL as exc:
        raise HTTPException(status_code=400, detail=f"OnTrack won't open this link: {exc}.")
    except OSError:
        pass        # can't look the name up right now: the download will say so


def require_key(x_api_key: str = Header(..., description="Your ONTRACK_API_KEY")):
    # compare_digest takes the same time whether the first or last character is
    # wrong, so an attacker can't guess the key one character at a time by timing.
    if not secrets.compare_digest(x_api_key, os.environ["ONTRACK_API_KEY"]):
        raise HTTPException(status_code=401, detail="Invalid API key")


# ------------------------------------------------------- errors -> HTTP codes

@app.exception_handler(NotFound)
async def not_found(_: Request, exc: NotFound):
    return JSONResponse(status_code=404, content={"detail": f"Not found: {exc}"})


@app.exception_handler(Duplicate)
async def duplicate(_: Request, exc: Duplicate):
    return JSONResponse(status_code=409, content={
        "detail": "This link is already saved.", "item_id": exc.item_id, "link_id": exc.link_id})


# ------------------------------------------------------------ request bodies
# Pydantic validates these automatically: a missing field or a price of "abc"
# gets a clear 422 error before our code ever runs.

class BudgetIn(BaseModel):
    amount: float = Field(..., ge=0, examples=[15000])


class FromLinkIn(BaseModel):
    url: HttpUrl
    name: str | None = Field(None, description="Optional; defaults to the product's title")
    priority: int = 0


class FromHtmlIn(BaseModel):
    url: HttpUrl
    html: str = Field(..., min_length=1, description="The product page as the phone downloaded it")
    name: str | None = None
    priority: int = 0


class ManualItemIn(BaseModel):
    name: str = Field(..., min_length=1, examples=["Charm bracelet"])
    price: float | None = Field(None, ge=0, examples=[1500])
    note: str | None = None
    priority: int = 0
    url: HttpUrl | None = None      # optional store link, saved without contacting the store


class LinkIn(BaseModel):
    url: HttpUrl


class ItemPatch(BaseModel):
    name: str | None = Field(None, min_length=1)
    status: Literal["planned", "later", "purchased"] | None = None
    priority: int | None = None
    manual_price: float | None = Field(None, ge=0)
    note: str | None = None
    purchased_price: float | None = Field(None, ge=0)


# ------------------------------------------------------------------- routes

auth = [Depends(require_key)]


@app.get("/health")
def health():
    """Unauthenticated ping, handy for checking the server is up."""
    return {"ok": True}


@app.get("/summary", dependencies=auth)
def get_summary(conn=Depends(get_db)):
    """Budget, discounted total of planned items, what's left, and every item."""
    return services.summary(conn)


@app.put("/budget", dependencies=auth)
def put_budget(body: BudgetIn, conn=Depends(get_db)):
    services.set_budget(conn, body.amount)
    return {"budget": body.amount}


@app.get("/items", dependencies=auth)
def get_items(status: Literal["planned", "later", "purchased", "all"] = "all", conn=Depends(get_db)):
    return services.list_items(conn, None if status == "all" else status)


@app.get("/items/{item_id}/history", dependencies=auth)
def get_item_history(item_id: int, conn=Depends(get_db)):
    """Every price check for this item's links, oldest first."""
    return services.price_history(conn, item_id)


@app.post("/items/from-link", status_code=201, dependencies=auth)
def post_from_link(body: FromLinkIn, conn=Depends(get_db), extract=Depends(get_extract),
                   resolve=Depends(get_resolver)):
    """Paste a product link. The item is created even if the price can't be read."""
    refuse_unsafe(str(body.url), resolve)
    item_id = services.create_item_from_link(conn, str(body.url), extract, body.name, body.priority)
    return services.item_view(conn, item_id)


# @app.post("/items/from-html", status_code=201, dependencies=auth)
# def post_from_html(body: FromHtmlIn, conn=Depends(get_db)):
#     """The phone fetched the page itself and sends it here; the server never contacts the store."""
#     print("from-html:", len(body.html), "chars | starts:", body.html[:80].replace("\n", " "))   # TEMP debug
#     extract = services.extract_from_html(body.html)
#     item_id = services.create_item_from_link(conn, str(body.url), extract, body.name, body.priority)
#     return services.item_view(conn, item_id)

@app.post("/items/from-html", status_code=201, dependencies=auth)
def post_from_html(url: HttpUrl = Form(...), html: UploadFile = File(...),
                   name: str | None = Form(None), priority: int = Form(0),
                   conn=Depends(get_db), extract=Depends(get_extract)):
    """The phone fetched the page and uploads it here. Non-Amazon pages fall back to a server fetch."""
    page = html.file.read().decode("utf-8", errors="replace")
    if not page.strip():
        raise HTTPException(status_code=422, detail="The uploaded page is empty")
    extract_fn = services.extract_from_html(page, fallback=extract)
    item_id = services.create_item_from_link(conn, str(url), extract_fn, name, priority)
    return services.item_view(conn, item_id)


@app.post("/items", status_code=201, dependencies=auth)
def post_manual(body: ManualItemIn, conn=Depends(get_db), resolve=Depends(get_resolver)):
    """An item you type in yourself: a name, a price, and optionally a store link."""
    if body.url:
        refuse_unsafe(str(body.url), resolve)
    item_id = services.create_manual_item(conn, body.name, body.price, body.note, body.priority,
                                          str(body.url) if body.url else None)
    return services.item_view(conn, item_id)


@app.get("/items/{item_id}", dependencies=auth)
def get_item(item_id: int, conn=Depends(get_db)):
    return services.item_view(conn, item_id)


@app.patch("/items/{item_id}", dependencies=auth)
def patch_item(item_id: int, body: ItemPatch, conn=Depends(get_db)):
    # exclude_unset: only change fields the request actually included,
    # so sending {"planned": false} doesn't wipe the name.
    services.update_item(conn, item_id, **body.model_dump(exclude_unset=True))
    return services.item_view(conn, item_id)


@app.delete("/items/{item_id}", status_code=204, dependencies=auth)
def remove_item(item_id: int, conn=Depends(get_db)):
    services.delete_item(conn, item_id)


@app.post("/items/{item_id}/links", status_code=201, dependencies=auth)
def post_link(item_id: int, body: LinkIn, conn=Depends(get_db), extract=Depends(get_extract),
              resolve=Depends(get_resolver)):
    """Add another store's link to an item; the cheapest one counts."""
    refuse_unsafe(str(body.url), resolve)
    services.add_link(conn, item_id, str(body.url), extract)
    return services.item_view(conn, item_id)


@app.delete("/links/{link_id}", status_code=204, dependencies=auth)
def remove_link(link_id: int, conn=Depends(get_db)):
    services.delete_link(conn, link_id)


@app.post("/refresh", dependencies=auth)
async def post_refresh(force: bool = False, conn=Depends(get_db), extract=Depends(get_extract)):
    """Re-check prices of links not checked in the last hour (all of them with ?force=true)."""
    return await services.refresh(conn, extract, force=force)


@app.post("/items/{item_id}/refresh", dependencies=auth)
async def post_item_refresh(item_id: int, force: bool = True,
                            conn=Depends(get_db), extract=Depends(get_extract)):
    """Re-check one item's links. Forced by default: you asked for this one specifically."""
    result = await services.refresh(conn, extract, force=force, item_id=item_id)
    return {**result, "item": services.item_view(conn, item_id)}

@app.get("/refresh/phone-list", dependencies=auth)
def get_phone_refresh_list(force: bool = False, conn=Depends(get_db)):
    """Amazon links the phone should download and upload back (bought items and recent checks skipped)."""
    return services.phone_refresh_list(conn, force)


@app.post("/links/{link_id}/from-html", dependencies=auth)
def post_link_from_html(link_id: int, html: UploadFile = File(...), conn=Depends(get_db)):
    """Upload a freshly downloaded page for one link; records the new price."""
    page = html.file.read().decode("utf-8", errors="replace")
    if not page.strip():
        raise HTTPException(status_code=422, detail="The uploaded page is empty")
    return services.refresh_link_from_html(conn, link_id, page)