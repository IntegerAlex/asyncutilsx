# SPDX-License-Identifier: LGPL-2.1-only
# Copyright (c) 2026 Akshat kotpalliwar (alias IntegerAlex)

"""Tests for asyncutilsx ASGI wrapper.

Production-grade: spec-compliant ASGI behavior with clear routing,
explicit typing, and fail-fast validation for invalid scopes.
"""

import logging
import pytest
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from asyncutilsx import (
    asyncplus,
    create_app,
    router,
    _route,
    _to_asgi_app,
    _multiplex_lifespan,
)
from fastapi import FastAPI
from socketio.asgi import ASGIApp
from socketio.async_server import AsyncServer


# --- _route: total over ASGI scope dicts --------------------------------------


class TestRoute:
    """Test pure _route: same scope → same route; does not mutate scope."""

    def test_websocket_returns_socketio(self):
        assert _route({"type": "websocket", "path": "/socket.io/"}, "/socket.io/") == "socketio"
        assert _route({"type": "websocket", "path": "/socket.io"}, "/socket.io/") == "socketio"
        # Websocket with non-matching path routes to fastapi
        assert _route({"type": "websocket", "path": "/"}, "/socket.io/") == "fastapi"

    def test_http_socketio_path_returns_socketio(self):
        assert _route({"type": "http", "path": "/socket.io/"}, "/socket.io/") == "socketio"
        assert _route({"type": "http", "path": "/socket.io/?EIO=4"}, "/socket.io/") == "socketio"

    def test_http_other_returns_fastapi(self):
        assert _route({"type": "http", "path": "/"}, "/socket.io/") == "fastapi"
        assert _route({"type": "http", "path": "/api"}, "/socket.io/") == "fastapi"

    def test_empty_scope_defaults_to_fastapi(self):
        assert _route({}, "/socket.io/") == "fastapi"

    def test_referential_transparency_same_scope_same_route(self):
        scope = {"type": "http", "path": "/"}
        assert _route(scope, "/socket.io/") == _route(scope, "/socket.io/") == "fastapi"

    def test_scope_missing_type_and_path_defaults_to_fastapi(self):
        assert _route({}, "/socket.io/") == "fastapi"
        assert _route({"other": "key"}, "/socket.io/") == "fastapi"

    def test_scope_type_none_treated_as_http(self):
        assert _route({"type": None, "path": "/"}, "/socket.io/") == "fastapi"
        assert _route({"type": None, "path": "/socket.io/"}, "/socket.io/") == "socketio"

    def test_scope_path_none_treated_as_empty_string(self):
        assert _route({"type": "http", "path": None}, "/socket.io/") == "fastapi"
        # Websocket with None path (treated as empty) doesn't match socketio_path, routes to fastapi
        assert _route({"type": "websocket", "path": None}, "/socket.io/") == "fastapi"

    def test_scope_type_non_string_treated_as_http(self):
        assert _route({"type": 1, "path": "/"}, "/socket.io/") == "fastapi"
        assert _route({"type": [], "path": "/"}, "/socket.io/") == "fastapi"

    def test_scope_path_non_string_treated_as_empty(self):
        assert _route({"type": "http", "path": 0}, "/socket.io/") == "fastapi"
        assert _route({"type": "http", "path": []}, "/socket.io/") == "fastapi"

    def test_asgi_lifespan_scope_routes_to_fastapi(self):
        assert _route({"type": "lifespan", "path": ""}, "/socket.io/") == "fastapi"

    def test_path_socket_io_no_trailing_slash_routes_to_socketio(self):
        assert _route({"type": "http", "path": "/socket.io"}, "/socket.io/") == "socketio"

    def test_path_case_sensitive_socket_io(self):
        assert _route({"type": "http", "path": "/Socket.IO/"}, "/socket.io/") == "fastapi"
        assert _route({"type": "http", "path": "/SOCKET.IO/"}, "/socket.io/") == "fastapi"

    def test_custom_socketio_path(self):
        assert _route({"type": "http", "path": "/custom/"}, "/custom/") == "socketio"
        assert _route({"type": "http", "path": "/custom"}, "/custom/") == "socketio"
        assert _route({"type": "http", "path": "/socket.io/"}, "/custom/") == "fastapi"

    def test_route_does_not_mutate_scope(self):
        scope = {"type": "http", "path": "/"}
        snapshot = dict(scope)
        _route(scope, "/socket.io/")
        assert scope == snapshot
        scope_with_none = {"type": None, "path": None}
        snapshot2 = {"type": None, "path": None}
        _route(scope_with_none, "/socket.io/")
        assert scope_with_none == snapshot2


# --- _route: property-based (Hypothesis) --------------------------------------


# Strategies for ASGI-like scope dicts (type/path optional, various value types).
_scope_type = st.sampled_from(["http", "websocket", "lifespan", "other", ""])
_scope_path = st.one_of(
    st.none(),
    st.text(alphabet="/abcdefghijklmnopqrstuvwxyz.?&=", min_size=0, max_size=200),
    st.integers(),
    st.lists(st.none()),
)
_scope_dict = st.dictionaries(
    keys=st.sampled_from(["type", "path", "extra"]),
    values=st.one_of(st.none(), st.text(max_size=50), st.integers(), st.lists(st.none())),
    min_size=0,
    max_size=5,
).map(lambda d: {k: v for k, v in d.items() if k in ("type", "path", "extra")})
_socketio_path = st.sampled_from(["/socket.io/", "/custom/", "/", "/a/"])


class TestRoutePropertyBased:
    """Property-based tests for _route: determinism, range, no mutation."""

    @given(scope=_scope_dict, socketio_path=_socketio_path)
    @settings(max_examples=500)
    def test_route_result_is_socketio_or_fastapi(self, scope, socketio_path):
        result = _route(scope, socketio_path)
        assert result in ("socketio", "fastapi")

    @given(scope=_scope_dict, socketio_path=_socketio_path)
    @settings(max_examples=500)
    def test_same_scope_same_route_determinism(self, scope, socketio_path):
        r1 = _route(scope, socketio_path)
        r2 = _route(scope, socketio_path)
        assert r1 == r2

    @given(scope=_scope_dict, socketio_path=_socketio_path)
    @settings(max_examples=300)
    def test_route_does_not_mutate_scope_pbt(self, scope, socketio_path):
        snapshot = dict(scope)
        _route(scope, socketio_path)
        assert scope == snapshot

    @given(scope=_scope_dict)
    @settings(max_examples=200)
    def test_websocket_type_gated_by_path(self, scope):
        scope = {**scope, "type": "websocket"}
        # Websocket routing is now gated by path matching, same as HTTP
        path = scope.get("path", "")
        if path and (path.startswith("/socket.io/") or path == "/socket.io"):
            assert _route(scope, "/socket.io/") == "socketio"
        else:
            assert _route(scope, "/socket.io/") == "fastapi"

    @given(
        path=st.sampled_from([
            "/", "/api", "/health", "/docs", "/openapi.json",
            "/v1", "/v1/users", "/foo", "/bar", "/static/x",
        ])
    )
    @settings(max_examples=50)
    def test_http_non_socketio_path_always_fastapi(self, path):
        scope = {"type": "http", "path": path}
        assert _route(scope, "/socket.io/") == "fastapi"
        assert _route(scope, "/custom/") == "fastapi"


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


# --- asyncplus() factory and returned ASGI app -------------------------------


class TestCreateApp:
    """Test create_app convenience function."""

    def test_returns_asgi_app_equivalent_to_asyncplus(self):
        app = FastAPI()
        sio = AsyncServer(async_mode="asgi")
        combined = create_app(app, sio)
        assert callable(combined)
        # Same as asyncplus(app, sio)
        expected = asyncplus(app, sio)
        assert callable(expected)


class TestAsyncplus:
    """Test asyncplus and returned asgi_app with spec-compliant scope handling."""

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

        scope = {"type": "websocket", "path": "/socket.io/"}
        receive = AsyncMock(return_value={"type": "websocket.disconnect"})
        send = AsyncMock()

        await combined(scope, receive, send)

    @pytest.mark.asyncio
    async def test_asgi_app_scope_none_raises_type_error(self):
        fastapi_app = AsyncMock()
        combined = asyncplus(fastapi_app, AsyncMock())
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        with pytest.raises(TypeError):
            await combined(None, receive, send)

    @pytest.mark.asyncio
    async def test_asgi_app_scope_not_dict_raises_type_error(self):
        fastapi_app = AsyncMock()
        combined = asyncplus(fastapi_app, AsyncMock())
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        with pytest.raises(TypeError):
            await combined([], receive, send)

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

    def test_socketio_path_with_spaces_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid characters"):
            asyncplus(FastAPI(), AsyncMock(), socketio_path="/custom path/")

    def test_socketio_path_with_tabs_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid characters"):
            asyncplus(FastAPI(), AsyncMock(), socketio_path="/custom\t/")

    @pytest.mark.asyncio
    async def test_custom_socketio_path_routes_to_socketio(self):
        sio_asgi = AsyncMock()
        fastapi_app = AsyncMock()
        combined = asyncplus(
            fastapi_app, sio_asgi, socketio_path="/custom/"
        )
        scope = {"type": "http", "path": "/custom/"}
        receive = AsyncMock(return_value={"type": "http.disconnect"})
        send = AsyncMock()
        await combined(scope, receive, send)
        sio_asgi.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_debug_hook_called_with_route_and_scope(self):
        debug_hook = MagicMock()
        combined = asyncplus(FastAPI(), AsyncMock(), debug_hook=debug_hook)
        scope = {"type": "http", "path": "/"}
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        await combined(scope, receive, send)
        debug_hook.assert_called_once_with("fastapi", scope)

    @pytest.mark.asyncio
    async def test_socketio_failure_falls_back_when_enabled(self, caplog):
        caplog.set_level(logging.INFO)
        fastapi_app = AsyncMock()
        sio_asgi = AsyncMock(side_effect=RuntimeError("reject"))
        combined = asyncplus(
            fastapi_app,
            sio_asgi,
            socketio_fallback_on_error=True,
        )
        scope = {"type": "http", "path": "/socket.io/"}
        receive = AsyncMock(return_value={"type": "http.disconnect"})
        send = AsyncMock()
        await combined(scope, receive, send)
        fastapi_app.assert_called_once_with(scope, receive, send)
        assert any(
            "Socket.IO" in record.message and "falling back" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_socketio_failure_raises_without_fallback(self, caplog):
        caplog.set_level(logging.WARNING)
        fastapi_app = AsyncMock()
        sio_asgi = AsyncMock(side_effect=RuntimeError("reject"))
        combined = asyncplus(
            fastapi_app,
            sio_asgi,
            socketio_fallback_on_error=False,
        )
        scope = {"type": "http", "path": "/socket.io/"}
        receive = AsyncMock(return_value={"type": "http.disconnect"})
        send = AsyncMock()
        with pytest.raises(RuntimeError):
            await combined(scope, receive, send)
        assert any(
            "Socket.IO rejected connection" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout_error_when_app_hangs(self):
        import asyncio

        async def hanging_app(scope, receive, send):
            """
            ASGI application that hangs indefinitely.
            
            Used to simulate a downstream app that never responds: the coroutine awaits an unresolved Future and therefore never sends events, never receives a completed message, and never returns.
            """
            await asyncio.Future()  # never completes

        fastapi_app = MagicMock()
        fastapi_app.side_effect = hanging_app
        combined = asyncplus(fastapi_app, AsyncMock(), timeout=0.05)
        scope = {"type": "http", "path": "/"}
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                combined(scope, receive, send),
                timeout=0.5,
            )

    @pytest.mark.asyncio
    async def test_accepts_asgi_app_as_socketio_arg(self):
        """
        Verify that asyncplus accepts a pre-wrapped ASGIApp as the socketio argument and routes a websocket scope to it.
        """
        sio = AsyncServer(async_mode="asgi")
        wrapped = ASGIApp(sio)
        combined = asyncplus(FastAPI(), wrapped)
        scope = {"type": "websocket", "path": "/"}
        receive = AsyncMock(return_value={"type": "websocket.disconnect"})
        send = AsyncMock()
        await combined(scope, receive, send)


# --- _multiplex_lifespan() ---------------------------------------------------


class TestLifespanMultiplexer:
    """Test that _multiplex_lifespan fans out lifespan events to both apps."""

    @pytest.mark.asyncio
    async def test_both_apps_receive_startup_and_shutdown(self):
        started = []
        stopped = []

        async def make_app(name):
            async def app(scope, receive, send):
                event = await receive()
                assert event["type"] == "lifespan.startup"
                started.append(name)
                await send({"type": "lifespan.startup.complete"})
                event = await receive()
                assert event["type"] == "lifespan.shutdown"
                stopped.append(name)
                await send({"type": "lifespan.shutdown.complete"})
            return app

        app1 = await make_app("app1")
        app2 = await make_app("app2")

        events = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        receive = AsyncMock(side_effect=events)
        send = AsyncMock()

        await _multiplex_lifespan({"type": "lifespan"}, receive, send, app1, app2)

        assert set(started) == {"app1", "app2"}
        assert set(stopped) == {"app1", "app2"}
        send.assert_any_call({"type": "lifespan.startup.complete"})
        send.assert_any_call({"type": "lifespan.shutdown.complete"})

    @pytest.mark.asyncio
    async def test_startup_failed_propagates(self):
        async def failing_app(scope, receive, send):
            await receive()
            await send({"type": "lifespan.startup.failed", "message": "oops"})

        async def ok_app(scope, receive, send):
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.complete"})

        events = [{"type": "lifespan.startup"}]
        receive = AsyncMock(side_effect=events)
        send = AsyncMock()

        await _multiplex_lifespan({"type": "lifespan"}, receive, send, failing_app, ok_app)

        calls = [c.args[0]["type"] for c in send.call_args_list]
        assert "lifespan.startup.failed" in calls
        assert "lifespan.startup.complete" not in calls

    @pytest.mark.asyncio
    async def test_app_without_lifespan_support_does_not_block(self):
        """An app that returns immediately without sending events should not block."""
        async def no_lifespan_app(scope, receive, send):
            return  # doesn't call receive or send

        async def normal_app(scope, receive, send):
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.complete"})

        events = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        receive = AsyncMock(side_effect=events)
        send = AsyncMock()

        await _multiplex_lifespan(
            {"type": "lifespan"}, receive, send, normal_app, no_lifespan_app
        )

        send.assert_any_call({"type": "lifespan.startup.complete"})
        send.assert_any_call({"type": "lifespan.shutdown.complete"})

    @pytest.mark.asyncio
    async def test_asyncplus_lifespan_reaches_both_apps(self):
        """asyncplus routes lifespan to both FastAPI and Socket.IO apps."""
        fastapi_started = []
        socketio_started = []

        async def fake_fastapi(scope, receive, send):
            if scope.get("type") == "lifespan":
                await receive()
                fastapi_started.append(True)
                await send({"type": "lifespan.startup.complete"})
                await receive()
                await send({"type": "lifespan.shutdown.complete"})

        async def fake_socketio(scope, receive, send):
            if scope.get("type") == "lifespan":
                await receive()
                socketio_started.append(True)
                await send({"type": "lifespan.startup.complete"})
                await receive()
                await send({"type": "lifespan.shutdown.complete"})

        fastapi_app = MagicMock()
        fastapi_app.side_effect = fake_fastapi
        sio_asgi = AsyncMock(side_effect=fake_socketio)

        combined = asyncplus(fastapi_app, sio_asgi)

        events = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        receive = AsyncMock(side_effect=events)
        send = AsyncMock()

        await combined({"type": "lifespan"}, receive, send)

        assert fastapi_started == [True]
        assert socketio_started == [True]
        send.assert_any_call({"type": "lifespan.startup.complete"})
        send.assert_any_call({"type": "lifespan.shutdown.complete"})

    @pytest.mark.asyncio
    async def test_shutdown_failed_propagates(self):
        """lifespan.shutdown.failed from an inner app must propagate to the server."""
        async def failing_shutdown_app(scope, receive, send):
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.failed", "message": "shutdown error"})

        async def ok_app(scope, receive, send):
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.complete"})

        events = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        receive = AsyncMock(side_effect=events)
        send = AsyncMock()

        await _multiplex_lifespan(
            {"type": "lifespan"}, receive, send, failing_shutdown_app, ok_app
        )

        calls = [c.args[0]["type"] for c in send.call_args_list]
        assert "lifespan.startup.complete" in calls
        assert "lifespan.shutdown.failed" in calls
        assert "lifespan.shutdown.complete" not in calls

    @pytest.mark.asyncio
    async def test_shutdown_exception_propagates_as_failed(self):
        """An exception raised by an app during shutdown must produce shutdown.failed."""
        async def raising_shutdown_app(scope, receive, send):
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            raise RuntimeError("crash during shutdown")

        async def ok_app(scope, receive, send):
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.complete"})

        events = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        receive = AsyncMock(side_effect=events)
        send = AsyncMock()

        await _multiplex_lifespan(
            {"type": "lifespan"}, receive, send, raising_shutdown_app, ok_app
        )

        calls = [c.args[0]["type"] for c in send.call_args_list]
        assert "lifespan.startup.complete" in calls
        assert "lifespan.shutdown.failed" in calls
        assert "lifespan.shutdown.complete" not in calls



# Users who need a /health endpoint can add one line of code in their own app.


# --- router() -----------------------------------------------------------------


class TestRouter:
    @pytest.mark.asyncio
    async def test_routes_by_predicate_with_default(self):
        websocket_app = AsyncMock()
        default_app = AsyncMock()
        routes = [(lambda s: s.get("type") == "websocket", websocket_app)]
        app = router(routes, default_app=default_app)

        scope = {"type": "websocket", "path": "/"}
        receive = AsyncMock(return_value={"type": "websocket.disconnect"})
        send = AsyncMock()
        await app(scope, receive, send)
        websocket_app.assert_called_once_with(scope, receive, send)

        http_scope = {"type": "http", "path": "/"}
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        await app(http_scope, receive, send)
        default_app.assert_called_once_with(http_scope, receive, send)

    @pytest.mark.asyncio
    async def test_no_default_app_raises(self):
        app = router([])
        scope = {"type": "http", "path": "/"}
        receive = AsyncMock(return_value={"type": "http.request"})
        send = AsyncMock()
        with pytest.raises(RuntimeError):
            await app(scope, receive, send)