"""Shared by every test file.

Logs (events.py) are written by a background thread on the live server. In
tests that thread is off: each test's events wait in the queue until the test
calls events.flush() itself, and are thrown away afterwards, so one test's
log lines can never land in the next test's database."""

import pytest

import events


@pytest.fixture(autouse=True)
def quiet_log_writer():
    events.background = False
    events.discard()
    yield
    events.discard()
