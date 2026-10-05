"""
FastAPI app: turns HTTP requests into calls to services.py.

Run locally:
    uvicorn main:app --reload
Then open http://127.0.0.1:8000/docs to try every endpoint in the browser.
"""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

import db
import services
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

# CORS: browsers block a web page from calling an API on a different origin
# (different host or port) unless the API explicitly allows it. The React app
# will run on localhost:5173 during development, so allow that.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ONTRACK_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        "detail": "This link is already saved.", "item_id": exc.item_id})


# ------------------------------------------------------------ request bodies
# Pydantic validates these automatically: a missing field or a price of "abc"
# gets a clear 422 error before our code ever runs.

class BudgetIn(BaseModel):
    amount: float = Field(..., ge=0, examples=[15000])


class FromLinkIn(BaseModel):
    url: HttpUrl
    name: str | None = Field(None, description="Optional; defaults to the product's title")
    priority: int = 0


class ManualItemIn(BaseModel):
    name: str = Field(..., min_length=1, examples=["Charm bracelet"])
    price: float | None = Field(None, ge=0, examples=[1500])
    note: str | None = None
    priority: int = 0


class LinkIn(BaseModel):
    url: HttpUrl


class ItemPatch(BaseModel):
    name: str | None = Field(None, min_length=1)
    status: Literal["planned", "later", "purchased"] | None = None
    priority: int | None = None
    manual_price: float | None = Field(None, ge=0)
    note: str | None = None


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


@app.post("/items/from-link", status_code=201, dependencies=auth)
def post_from_link(body: FromLinkIn, conn=Depends(get_db), extract=Depends(get_extract)):
    """Paste a product link. The item is created even if the price can't be read."""
    item_id = services.create_item_from_link(conn, str(body.url), extract, body.name, body.priority)
    return services.item_view(conn, item_id)


@app.post("/items", status_code=201, dependencies=auth)
def post_manual(body: ManualItemIn, conn=Depends(get_db)):
    """An item with a typed price and no link (e.g. a Come Again bracelet)."""
    item_id = services.create_manual_item(conn, body.name, body.price, body.note, body.priority)
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
def post_link(item_id: int, body: LinkIn, conn=Depends(get_db), extract=Depends(get_extract)):
    """Add another store's link to an item; the cheapest one counts."""
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
