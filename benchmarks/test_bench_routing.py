# SPDX-License-Identifier: LGPL-2.1-only
# Copyright (c) 2026 Akshat kotpalliwar (alias IntegerAlex)

"""Benchmarks for asyncutilsx routing logic.

These benchmarks measure the performance of the core routing decision function
and the ASGI wrapper creation, which are critical hot paths in the library.
"""

import pytest
from asyncutilsx import _route, _to_asgi_app, asyncplus
from fastapi import FastAPI
from socketio.async_server import AsyncServer


@pytest.mark.benchmark
def test_route_http_fastapi():
    """Benchmark routing decision for HTTP requests to FastAPI."""
    scope = {"type": "http", "path": "/api/users"}
    _route(scope)


@pytest.mark.benchmark
def test_route_http_socketio():
    """Benchmark routing decision for HTTP requests to Socket.IO."""
    scope = {"type": "http", "path": "/socket.io/?EIO=4"}
    _route(scope)


@pytest.mark.benchmark
def test_route_websocket():
    """Benchmark routing decision for WebSocket connections."""
    scope = {"type": "websocket", "path": "/ws"}
    _route(scope)


@pytest.mark.benchmark
def test_route_edge_case_none():
    """Benchmark routing decision for edge case (None scope)."""
    _route(None)


@pytest.mark.benchmark
def test_route_edge_case_empty():
    """Benchmark routing decision for edge case (empty scope)."""
    _route({})


@pytest.mark.benchmark
def test_to_asgi_app_wrap():
    """Benchmark wrapping AsyncServer in ASGIApp."""
    sio = AsyncServer(async_mode="asgi")
    _to_asgi_app(sio)


@pytest.mark.benchmark
def test_asyncplus_creation():
    """Benchmark creating the combined ASGI app."""
    app = FastAPI()
    sio = AsyncServer(async_mode="asgi")
    asyncplus(app, sio)
