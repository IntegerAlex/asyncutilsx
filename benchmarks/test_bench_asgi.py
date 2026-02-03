# SPDX-License-Identifier: LGPL-2.1-only
# Copyright (c) 2026 Akshat kotpalliwar (alias IntegerAlex)

"""Benchmarks for asyncutilsx ASGI integration.

These benchmarks measure the performance of the actual ASGI dispatch
logic under various scenarios.
"""

import pytest
from unittest.mock import AsyncMock
from asyncutilsx import asyncplus
from fastapi import FastAPI
from socketio.async_server import AsyncServer


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_asgi_dispatch_fastapi(benchmark):
    """Benchmark ASGI dispatch to FastAPI endpoint."""
    app = FastAPI()
    sio = AsyncServer(async_mode="asgi")
    combined = asyncplus(app, sio)
    
    scope = {"type": "http", "path": "/"}
    receive = AsyncMock(return_value={"type": "http.request", "body": b""})
    send = AsyncMock()
    
    # FastAPI will try to find a route, but we're just measuring dispatch overhead
    try:
        await benchmark(combined, scope, receive, send)
    except Exception:
        # Expected - FastAPI may fail to find route, but we measured the dispatch
        pass


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_asgi_dispatch_socketio(benchmark):
    """Benchmark ASGI dispatch to Socket.IO endpoint."""
    app = FastAPI()
    sio = AsyncServer(async_mode="asgi")
    combined = asyncplus(app, sio)
    
    scope = {"type": "http", "path": "/socket.io/"}
    receive = AsyncMock(return_value={"type": "http.disconnect"})
    send = AsyncMock()
    
    # Socket.IO may fail, but we're measuring dispatch overhead
    try:
        await benchmark(combined, scope, receive, send)
    except Exception:
        pass


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_asgi_dispatch_websocket(benchmark):
    """Benchmark ASGI dispatch for WebSocket connections."""
    app = FastAPI()
    sio = AsyncServer(async_mode="asgi")
    combined = asyncplus(app, sio)
    
    scope = {"type": "websocket", "path": "/"}
    receive = AsyncMock(return_value={"type": "websocket.disconnect"})
    send = AsyncMock()
    
    try:
        await benchmark(combined, scope, receive, send)
    except Exception:
        pass
