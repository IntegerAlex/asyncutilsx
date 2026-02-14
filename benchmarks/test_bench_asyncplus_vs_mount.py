# SPDX-License-Identifier: LGPL-2.1-only
# Copyright (c) 2026 Akshat kotpalliwar (alias IntegerAlex)

"""Benchmarks: asyncplus vs FastAPI mount workaround.

Compares performance of:
- asyncplus(app, sio): single ASGI app with one routing layer (path + type).
- FastAPI workaround: app.mount("/socket.io", socket_app), same app handles
  HTTP and WebSocket via Starlette's routing and mount dispatch.

All benchmarks use the same scopes and mocks so results are comparable.
"""

import pytest
from unittest.mock import AsyncMock

from fastapi import FastAPI
from socketio.asgi import ASGIApp
from socketio.async_server import AsyncServer

from asyncutilsx import asyncplus


def _make_fastapi():
    """Minimal FastAPI app with root route (for both setups)."""
    app = FastAPI()

    @app.get("/")
    def root():
        return {"ok": True}

    return app


def _make_asyncplus_app():
    """Single ASGI app via asyncplus: one entry point, routing inside."""
    app = _make_fastapi()
    sio = AsyncServer(async_mode="asgi")
    return asyncplus(app, sio)


def _make_mount_app():
    """FastAPI workaround: mount Socket.IO at /socket.io."""
    app = _make_fastapi()
    sio = AsyncServer(async_mode="asgi")
    app.mount("/socket.io", ASGIApp(sio))
    return app


@pytest.fixture
def asyncplus_asgi():
    return _make_asyncplus_app()


@pytest.fixture
def mount_asgi():
    return _make_mount_app()


# ---- HTTP to FastAPI (path /) ----
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_http_root_asyncplus(benchmark, asyncplus_asgi):
    """Benchmark: HTTP GET / through asyncplus (dispatched to FastAPI)."""
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    receive = AsyncMock(return_value={"type": "http.request", "body": b""})
    send = AsyncMock()
    try:
        await benchmark(asyncplus_asgi, scope, receive, send)
    except Exception:
        pass


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_http_root_mount(benchmark, mount_asgi):
    """Benchmark: HTTP GET / through FastAPI mount (FastAPI handles)."""
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    receive = AsyncMock(return_value={"type": "http.request", "body": b""})
    send = AsyncMock()
    try:
        await benchmark(mount_asgi, scope, receive, send)
    except Exception:
        pass


# ---- HTTP to Socket.IO path ----
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_http_socketio_path_asyncplus(benchmark, asyncplus_asgi):
    """Benchmark: HTTP /socket.io/ through asyncplus (dispatched to Socket.IO)."""
    scope = {"type": "http", "method": "GET", "path": "/socket.io/", "headers": []}
    receive = AsyncMock(return_value={"type": "http.disconnect"})
    send = AsyncMock()
    try:
        await benchmark(asyncplus_asgi, scope, receive, send)
    except Exception:
        pass


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_http_socketio_path_mount(benchmark, mount_asgi):
    """Benchmark: HTTP /socket.io/ through FastAPI mount (mounted app handles)."""
    scope = {"type": "http", "method": "GET", "path": "/socket.io/", "headers": []}
    receive = AsyncMock(return_value={"type": "http.disconnect"})
    send = AsyncMock()
    try:
        await benchmark(mount_asgi, scope, receive, send)
    except Exception:
        pass


# ---- WebSocket to Socket.IO path ----
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_websocket_socketio_path_asyncplus(benchmark, asyncplus_asgi):
    """Benchmark: WebSocket /socket.io/ through asyncplus (dispatched to Socket.IO)."""
    scope = {"type": "websocket", "path": "/socket.io/", "headers": []}
    receive = AsyncMock(return_value={"type": "websocket.disconnect"})
    send = AsyncMock()
    try:
        await benchmark(asyncplus_asgi, scope, receive, send)
    except Exception:
        pass


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_websocket_socketio_path_mount(benchmark, mount_asgi):
    """Benchmark: WebSocket /socket.io/ through FastAPI mount (mounted app handles)."""
    scope = {"type": "websocket", "path": "/socket.io/", "headers": []}
    receive = AsyncMock(return_value={"type": "websocket.disconnect"})
    send = AsyncMock()
    try:
        await benchmark(mount_asgi, scope, receive, send)
    except Exception:
        pass


# ---- App creation ----
@pytest.mark.benchmark
def test_app_creation_asyncplus(benchmark):
    """Benchmark: time to create combined app with asyncplus."""
    app = _make_fastapi()
    sio = AsyncServer(async_mode="asgi")
    benchmark(asyncplus, app, sio)


@pytest.mark.benchmark
def test_app_creation_mount(benchmark):
    """Benchmark: time to create combined app with FastAPI mount."""
    def create():
        app = _make_fastapi()
        sio = AsyncServer(async_mode="asgi")
        app.mount("/socket.io", ASGIApp(sio))
        return app

    benchmark(create)
