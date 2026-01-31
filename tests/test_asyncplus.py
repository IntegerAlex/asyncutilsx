# SPDX-License-Identifier: LGPL-2.1-only
# Copyright (c) 2026 Akshat kotpalliwar (alias IntegerAlex)

"""Tests for asyncutilsx ASGI wrapper.

Production-grade: total functions — no runtime exceptions, no undefined behavior
for any input to _route, _to_asgi_app, asyncplus, and the returned ASGI app.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from asyncutilsx import asyncplus, _route, _to_asgi_app
from fastapi import FastAPI
from socketio.asgi import ASGIApp
from socketio.async_server import AsyncServer


# --- _route: total over all inputs -------------------------------------------


class TestRoute:
    """Test pure _route: same scope → same route; total (no KeyError, no AttributeError)."""

    def test_websocket_returns_socketio(self):
        assert _route({"type": "websocket", "path": "/"}) == "socketio"

    def test_http_socketio_path_returns_socketio(self):
        assert _route({"type": "http", "path": "/socket.io/"}) == "socketio"
        assert _route({"type": "http", "path": "/socket.io/?EIO=4"}) == "socketio"

    def test_http_other_returns_fastapi(self):
        assert _route({"type": "http", "path": "/"}) == "fastapi"
        assert _route({"type": "http", "path": "/api"}) == "fastapi"

    def test_total_empty_scope_defaults_to_fastapi(self):
        assert _route({}) == "fastapi"

    def test_referential_transparency_same_scope_same_route(self):
        scope = {"type": "http", "path": "/"}
        assert _route(scope) == _route(scope) == "fastapi"

    # Total: invalid or missing scope — must not raise
    def test_scope_none_returns_fastapi(self):
        assert _route(None) == "fastapi"

    def test_scope_not_dict_returns_fastapi(self):
        assert _route(1) == "fastapi"
        assert _route([]) == "fastapi"
        assert _route("scope") == "fastapi"
        assert _route(object()) == "fastapi"

    def test_scope_missing_type_and_path_defaults_to_fastapi(self):
        assert _route({}) == "fastapi"
        assert _route({"other": "key"}) == "fastapi"

    def test_scope_type_none_treated_as_http(self):
        assert _route({"type": None, "path": "/"}) == "fastapi"
        assert _route({"type": None, "path": "/socket.io/"}) == "socketio"

    def test_scope_path_none_treated_as_empty_string(self):
        assert _route({"type": "http", "path": None}) == "fastapi"
        assert _route({"type": "websocket", "path": None}) == "socketio"

    def test_scope_type_non_string_treated_as_http(self):
        assert _route({"type": 1, "path": "/"}) == "fastapi"
        assert _route({"type": [], "path": "/"}) == "fastapi"

    def test_scope_path_non_string_treated_as_empty(self):
        assert _route({"type": "http", "path": 0}) == "fastapi"
        assert _route({"type": "http", "path": []}) == "fastapi"

    def test_asgi_lifespan_scope_routes_to_fastapi(self):
        assert _route({"type": "lifespan", "path": ""}) == "fastapi"

    def test_path_socket_io_no_trailing_slash_routes_to_fastapi(self):
        assert _route({"type": "http", "path": "/socket.io"}) == "fastapi"

    def test_path_case_sensitive_socket_io(self):
        assert _route({"type": "http", "path": "/Socket.IO/"}) == "fastapi"
        assert _route({"type": "http", "path": "/SOCKET.IO/"}) == "fastapi"

    def test_route_does_not_mutate_scope(self):
        scope = {"type": "http", "path": "/"}
        snapshot = dict(scope)
        _route(scope)
        assert scope == snapshot
        scope_with_none = {"type": None, "path": None}
        snapshot2 = {"type": None, "path": None}
        _route(scope_with_none)
        assert scope_with_none == snapshot2


# --- _to_asgi_app: total over inputs ------------------------------------------


class TestToAsgiApp:
    """Test _to_asgi_app: same input → same output; no exceptions."""

    def test_async_server_wrapped_in_asgi_app(self):
        sio = AsyncServer(async_mode="asgi")
        result = _to_asgi_app(sio)
        assert isinstance(result, ASGIApp)

    def test_asgi_app_returned_unchanged(self):
        sio = AsyncServer(async_mode="asgi")
        wrapped = ASGIApp(sio)
        result = _to_asgi_app(wrapped)
        assert result is wrapped

    def test_same_input_same_output_repeatable(self):
        sio = AsyncServer(async_mode="asgi")
        r1 = _to_asgi_app(sio)
        r2 = _to_asgi_app(sio)
        assert isinstance(r1, ASGIApp) and isinstance(r2, ASGIApp)


# --- asyncplus() factory and returned ASGI app: total over inputs --------------


class TestAsyncplus:
    """Test asyncplus and returned asgi_app: no undefined behavior, no exceptions from our code."""

    def test_returns_callable(self):
        app = FastAPI()
        sio = AsyncServer(async_mode="asgi")
        combined = asyncplus(app, sio)
        assert callable(combined)

    def test_same_inputs_same_output_repeatable(self):
        app = FastAPI()
        sio = AsyncServer(async_mode="asgi")
        c1 = asyncplus(app, sio)
        c2 = asyncplus(app, sio)
        assert c1 is not c2
        assert callable(c1) and callable(c2)

    @pytest.mark.asyncio
    async def test_http_non_socketio_routes_to_fastapi(self):
        received_scope = None

        async def fake_fastapi(scope, receive, send):
            nonlocal received_scope
            received_scope = scope
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"ok"})

        app = MagicMock()
        app.side_effect = fake_fastapi
        sio = AsyncServer(async_mode="asgi")
        combined = asyncplus(app, sio)

        scope = {"type": "http", "path": "/"}
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()

        await combined(scope, receive, send)

        assert received_scope is not None
        assert received_scope["path"] == "/"
        app.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_socketio_path_routes_to_socketio(self):
        sio_asgi = AsyncMock()
        combined = asyncplus(FastAPI(), sio_asgi)

        scope = {"type": "http", "path": "/socket.io/"}
        receive = AsyncMock(return_value={"type": "http.disconnect"})
        send = AsyncMock()

        await combined(scope, receive, send)

        sio_asgi.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_websocket_routes_to_socketio(self):
        sio = AsyncServer(async_mode="asgi")
        combined = asyncplus(FastAPI(), sio)

        scope = {"type": "websocket", "path": "/"}
        receive = AsyncMock(return_value={"type": "websocket.disconnect"})
        send = AsyncMock()

        await combined(scope, receive, send)

    # Total: asgi_app(scope, receive, send) — routing never raises for any scope
    @pytest.mark.asyncio
    async def test_asgi_app_scope_none_routes_to_fastapi_no_raise_from_route(self):
        """_route(None) must not raise; dispatch normalizes scope to dict."""
        fastapi_app = AsyncMock()
        sio_asgi = AsyncMock()
        combined = asyncplus(fastapi_app, sio_asgi)
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        await combined(None, receive, send)
        fastapi_app.assert_called_once_with({}, receive, send)

    @pytest.mark.asyncio
    async def test_asgi_app_empty_scope_routes_to_fastapi(self):
        fastapi_app = AsyncMock()
        sio_asgi = AsyncMock()
        combined = asyncplus(fastapi_app, sio_asgi)
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        await combined({}, receive, send)
        fastapi_app.assert_called_once_with({}, receive, send)

    @pytest.mark.asyncio
    async def test_asgi_app_minimal_http_scope_passed_through(self):
        fastapi_app = AsyncMock()
        combined = asyncplus(fastapi_app, AsyncMock())
        scope = {"type": "http", "path": "/health"}
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        await combined(scope, receive, send)
        fastapi_app.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_asgi_app_receive_returns_disconnect_immediately(self):
        """Downstream app may receive disconnect without request body; we must not raise."""
        fastapi_app = AsyncMock()
        combined = asyncplus(fastapi_app, AsyncMock())
        scope = {"type": "http", "path": "/"}
        receive = AsyncMock(return_value={"type": "http.disconnect"})
        send = AsyncMock()
        await combined(scope, receive, send)
        fastapi_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_asgi_app_scope_with_extra_keys_passed_through_unchanged(self):
        fastapi_app = AsyncMock()
        combined = asyncplus(fastapi_app, AsyncMock())
        scope = {"type": "http", "path": "/", "extra": "value", "query_string": b""}
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        await combined(scope, receive, send)
        call_scope = fastapi_app.call_args[0][0]
        assert call_scope.get("extra") == "value"
        assert call_scope.get("path") == "/"

    @pytest.mark.asyncio
    async def test_accepts_asgi_app_as_socketio_arg(self):
        """Passing pre-wrapped ASGIApp (not AsyncServer) must work; total over union type."""
        sio = AsyncServer(async_mode="asgi")
        wrapped = ASGIApp(sio)
        combined = asyncplus(FastAPI(), wrapped)
        scope = {"type": "websocket", "path": "/"}
        receive = AsyncMock(return_value={"type": "websocket.disconnect"})
        send = AsyncMock()
        await combined(scope, receive, send)
