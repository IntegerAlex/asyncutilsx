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

SOCKETIO_PATH = "/socket.io/"


@pytest.mark.benchmark
def test_route_http_fastapi(benchmark):
    """Benchmark routing decision for HTTP requests to FastAPI."""
    scope = {"type": "http", "path": "/api/users"}
    benchmark(_route, scope, SOCKETIO_PATH)


@pytest.mark.benchmark
def test_route_http_socketio(benchmark):
    """Benchmark routing decision for HTTP requests to Socket.IO."""
    scope = {"type": "http", "path": "/socket.io/?EIO=4"}
    benchmark(_route, scope, SOCKETIO_PATH)


@pytest.mark.benchmark
def test_route_websocket_socketio_path(benchmark):
    """Benchmark routing decision for WebSocket to Socket.IO path."""
    scope = {"type": "websocket", "path": "/socket.io/"}
    benchmark(_route, scope, SOCKETIO_PATH)


@pytest.mark.benchmark
def test_route_websocket_other_path(benchmark):
    """Benchmark routing decision for WebSocket to non-Socket.IO path."""
    scope = {"type": "websocket", "path": "/ws"}
    benchmark(_route, scope, SOCKETIO_PATH)


@pytest.mark.benchmark
def test_route_edge_case_empty(benchmark):
    """Benchmark routing decision for edge case (empty scope)."""
    scope = {}
    benchmark(_route, scope, SOCKETIO_PATH)


@pytest.mark.benchmark
def test_to_asgi_app_wrap(benchmark):
    """Benchmark wrapping AsyncServer in ASGIApp."""
    sio = AsyncServer(async_mode="asgi")
    benchmark(_to_asgi_app, sio)


@pytest.mark.benchmark
def test_asyncplus_creation(benchmark):
    """Benchmark creating the combined ASGI app."""
    app = FastAPI()
    sio = AsyncServer(async_mode="asgi")

    def create():
        return asyncplus(app, sio)

    benchmark(create)
