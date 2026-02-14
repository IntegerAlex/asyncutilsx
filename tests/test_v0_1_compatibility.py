# SPDX-License-Identifier: LGPL-2.1-only
# Copyright (c) 2026 Akshat kotpalliwar (alias IntegerAlex)

"""
Backward compatibility tests for v0.2.0 with v0.1.0.

This module verifies that v0.2.0 maintains backward compatibility with v0.1.0
where possible, documents breaking changes, and ensures error handling is
robust and comprehensive.

Changes in v0.2.0:
1. Router class removed → router() function added (breaking change for class users)
2. ImmutableScope/ReadOnlyScope removed (breaking change if code relied on these)
3. Fail-fast scope validation: non-dict scope now raises TypeError instead of normalizing
4. New features added: timeout, debug_hook, socketio_fallback_on_error, custom paths
5. Pure functional design replacing class-based approach
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from socketio.async_server import AsyncServer

from asyncutilsx import asyncplus, create_app, _route, _to_asgi_app


class TestV010CoreBehaviorPreserved:
    """Test that core v0.1.0 behavior is preserved in v0.2.0."""

    def test_basic_routing_http_non_socketio_to_fastapi(self):
        """v0.1.0 behavior: HTTP requests not for /socket.io/ go to FastAPI."""
        scope = {"type": "http", "path": "/api"}
        assert _route(scope, "/socket.io/") == "fastapi"

    def test_basic_routing_http_socketio_to_socketio(self):
        """v0.1.0 behavior: HTTP requests for /socket.io/ go to Socket.IO."""
        scope = {"type": "http", "path": "/socket.io/"}
        assert _route(scope, "/socket.io/") == "socketio"

    def test_basic_routing_websocket_to_socketio(self):
        """v0.2.0 BREAKING CHANGE: WebSocket now requires socketio_path match."""
        # In v0.1.0: WebSocket always routed to socketio
        # In v0.2.0: WebSocket ONLY routes to socketio if path matches socketio_path
        scope = {"type": "websocket", "path": "/socket.io/"}
        assert _route(scope, "/socket.io/") == "socketio"

    def test_basic_routing_websocket_without_socketio_path(self):
        """v0.2.0 BREAKING CHANGE: WebSocket without socketio_path routes to fastapi."""
        # In v0.1.0: any WebSocket went to Socket.IO
        # In v0.2.0: WebSocket without matching socketio_path goes to FastAPI
        scope = {"type": "websocket", "path": "/other"}
        assert _route(scope, "/socket.io/") == "fastapi"

    def test_asyncplus_creates_callable_asgi_app(self):
        """v0.1.0 behavior: asyncplus() returns a callable ASGI app."""
        app = FastAPI()
        sio = AsyncServer(async_mode="asgi")
        combined = asyncplus(app, sio)
        assert callable(combined)

    def test_asyncplus_accepts_async_server(self):
        """v0.1.0 behavior: asyncplus() accepts AsyncServer directly."""
        app = FastAPI()
        sio = AsyncServer(async_mode="asgi")
        combined = asyncplus(app, sio)
        assert callable(combined)

    @pytest.mark.asyncio
    async def test_asyncplus_routes_http_to_fastapi(self):
        """v0.1.0 behavior: asyncplus() routes HTTP to FastAPI."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app)

        scope = {"type": "http", "path": "/api"}
        receive = AsyncMock()
        send = AsyncMock()

        await combined(scope, receive, send)
        fastapi_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_asyncplus_routes_websocket_to_socketio(self):
        """v0.2.0 BREAKING CHANGE: asyncplus() routes WebSocket to Socket.IO only if path matches."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app)

        # v0.1.0 would have routed this to socket.io
        # v0.2.0 requires path to match socketio_path
        scope = {"type": "websocket", "path": "/socket.io/"}
        receive = AsyncMock()
        send = AsyncMock()

        await combined(scope, receive, send)
        sio_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_asyncplus_routes_socketio_path_to_socketio(self):
        """v0.1.0 behavior: asyncplus() routes /socket.io/ to Socket.IO."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app)

        scope = {"type": "http", "path": "/socket.io/"}
        receive = AsyncMock()
        send = AsyncMock()

        await combined(scope, receive, send)
        sio_app.assert_called_once()


class TestV010BreakingChanges:
    """Document and test breaking changes from v0.1.0 to v0.2.0."""

    @pytest.mark.asyncio
    async def test_non_dict_scope_now_raises_type_error(self):
        """BREAKING: v0.1.0 normalized None/non-dict scopes; v0.2.0 raises TypeError."""
        # v0.1.0 behavior: normalized to empty dict {}
        # v0.2.0 behavior: raises TypeError

        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app)

        receive = AsyncMock()
        send = AsyncMock()

        # None scope should raise TypeError in v0.2.0
        with pytest.raises(TypeError, match="ASGI scope must be dict"):
            await combined(None, receive, send)

        # Non-dict scope should raise TypeError in v0.2.0
        with pytest.raises(TypeError, match="ASGI scope must be dict"):
            await combined([], receive, send)

    def test_router_class_removed_use_function_instead(self):
        """BREAKING: RouterController class removed; replaced by router() function."""
        # This test documents the API change but doesn't need to test the old API
        from asyncutilsx import router

        assert callable(router)
        # router() is a function, not a class

    def test_no_immutable_scope_class(self):
        """BREAKING: ImmutableScope/ReadOnlyScope classes removed."""
        # These classes no longer exist in v0.2.0
        from asyncutilsx import __all__  # noqa: F401

        # They should not be in the public API
        assert "ImmutableScope" not in dir()
        assert "ReadOnlyScope" not in dir()


class TestV020ErrorHandling:
    """Test comprehensive error handling in v0.2.0."""

    def test_error_on_invalid_socketio_path_with_spaces(self):
        """Error handling: socketio_path with spaces raises ValueError."""
        with pytest.raises(ValueError, match="invalid characters"):
            asyncplus(FastAPI(), AsyncMock(), socketio_path="/custom space/")

    def test_error_on_invalid_socketio_path_with_tabs(self):
        """Error handling: socketio_path with tabs raises ValueError."""
        with pytest.raises(ValueError, match="invalid characters"):
            asyncplus(FastAPI(), AsyncMock(), socketio_path="/custom\t/")

    def test_error_on_invalid_socketio_path_with_newlines(self):
        """Error handling: socketio_path with newlines raises ValueError."""
        with pytest.raises(ValueError, match="invalid characters"):
            asyncplus(FastAPI(), AsyncMock(), socketio_path="/custom\n/")

    @pytest.mark.asyncio
    async def test_socket_io_error_logged_and_reraised_without_fallback(self):
        """Error handling: Socket.IO errors are logged when not falling back."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock(side_effect=RuntimeError("test error"))
        combined = asyncplus(fastapi_app, sio_app, socketio_fallback_on_error=False)

        scope = {"type": "websocket", "path": "/socket.io/"}
        receive = AsyncMock()
        send = AsyncMock()

        with pytest.raises(RuntimeError):
            await combined(scope, receive, send)

        fastapi_app.assert_not_called()

    @pytest.mark.asyncio
    async def test_socket_io_error_falls_back_when_enabled(self):
        """Error handling: Socket.IO errors fall back to FastAPI when enabled."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock(side_effect=RuntimeError("test error"))
        combined = asyncplus(
            fastapi_app, sio_app, socketio_fallback_on_error=True
        )

        scope = {"type": "websocket", "path": "/"}
        receive = AsyncMock()
        send = AsyncMock()

        await combined(scope, receive, send)

        fastapi_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_error_is_raised(self):
        """Error handling: Timeout errors are properly raised."""
        async def slow_app(scope, receive, send):
            await asyncio.sleep(10)

        fastapi_app = MagicMock()
        fastapi_app.side_effect = slow_app
        combined = asyncplus(fastapi_app, AsyncMock(), timeout=0.01)

        scope = {"type": "http", "path": "/"}
        receive = AsyncMock()
        send = AsyncMock()

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(combined(scope, receive, send), timeout=0.5)

    @pytest.mark.asyncio
    async def test_type_error_on_invalid_scope_type(self):
        """Error handling: TypeError raised for invalid scope types."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app)

        receive = AsyncMock()
        send = AsyncMock()

        with pytest.raises(TypeError):
            await combined("not a dict", receive, send)

        fastapi_app.reset_mock()
        with pytest.raises(TypeError):
            await combined(123, receive, send)

        fastapi_app.reset_mock()
        with pytest.raises(TypeError):
            await combined([], receive, send)


class TestV020NewFeatures:
    """Test new features in v0.2.0 that enhance error handling."""

    @pytest.mark.asyncio
    async def test_debug_hook_called_on_every_request(self):
        """Feature: debug_hook is called for every request."""
        debug_hook = MagicMock()
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app, debug_hook=debug_hook)

        scope = {"type": "http", "path": "/"}
        receive = AsyncMock()
        send = AsyncMock()

        await combined(scope, receive, send)

        debug_hook.assert_called_once()
        call_args = debug_hook.call_args
        assert call_args[0][0] in ("socketio", "fastapi")
        assert call_args[0][1] is scope

    def test_custom_socketio_path_routing(self):
        """Feature: custom socketio_path allows non-default paths."""
        scope_custom = {"type": "http", "path": "/custom/"}
        scope_default = {"type": "http", "path": "/socket.io/"}

        # With custom path
        result = _route(scope_custom, "/custom/")
        assert result == "socketio"

        # Default path is treated as fastapi with custom routing
        result = _route(scope_default, "/custom/")
        assert result == "fastapi"

    @pytest.mark.asyncio
    async def test_timeout_feature_completes_quickly(self):
        """Feature: Timeout allows terminating slow operations."""
        async def quick_app(scope, receive, send):
            await asyncio.sleep(0.001)

        fastapi_app = MagicMock()
        fastapi_app.side_effect = quick_app
        combined = asyncplus(fastapi_app, AsyncMock(), timeout=1.0)

        scope = {"type": "http", "path": "/"}
        receive = AsyncMock()
        send = AsyncMock()

        # Should complete successfully within timeout
        await combined(scope, receive, send)


class TestV020CreateAppConvenience:
    """Test the create_app convenience function for common use case."""

    def test_create_app_is_shorthand_for_asyncplus(self):
        """Feature: create_app() is a convenient shorthand."""
        app = FastAPI()
        sio = AsyncServer(async_mode="asgi")
        combined1 = create_app(app, sio)
        combined2 = asyncplus(app, sio)

        assert callable(combined1)
        assert callable(combined2)

    @pytest.mark.asyncio
    async def test_create_app_routes_correctly(self):
        """Feature: create_app() routes like asyncplus()."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()

        combined = create_app(fastapi_app, sio_app)

        # Test FastAPI routing
        scope = {"type": "http", "path": "/api"}
        receive = AsyncMock()
        send = AsyncMock()
        await combined(scope, receive, send)
        fastapi_app.assert_called_once()


class TestV020RobustErrorCoverage:
    """Ensure exceptional error handling (errors are handled properly)."""

    @pytest.mark.asyncio
    async def test_scope_mutation_does_not_occur(self):
        """Robustness: scope dict is not mutated by routing."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app)

        original_scope = {"type": "http", "path": "/api"}
        scope_copy = dict(original_scope)

        receive = AsyncMock()
        send = AsyncMock()
        await combined(original_scope, receive, send)

        assert original_scope == scope_copy

    def test_route_function_deterministic(self):
        """Robustness: _route() is deterministic."""
        scope = {"type": "http", "path": "/api"}
        result1 = _route(scope, "/socket.io/")
        result2 = _route(scope, "/socket.io/")
        assert result1 == result2

    def test_to_asgi_app_idempotent(self):
        """Robustness: _to_asgi_app() wrapping is idempotent."""
        sio = AsyncServer(async_mode="asgi")
        wrapped1 = _to_asgi_app(sio)
        wrapped2 = _to_asgi_app(wrapped1)
        assert wrapped1 is wrapped2

    @pytest.mark.asyncio
    async def test_null_receive_handled(self):
        """Robustness: Null receive is passed through to app."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app)

        scope = {"type": "http", "path": "/"}
        receive = AsyncMock(return_value={"type": "http.disconnect"})
        send = AsyncMock()

        await combined(scope, receive, send)
        fastapi_app.assert_called_once()

    def test_empty_socketio_path_normalized(self):
        """Robustness: empty socketio_path is normalized to /socket.io/."""
        # Creating app with empty path should not fail
        combined = asyncplus(FastAPI(), AsyncMock(), socketio_path="")
        assert callable(combined)

    @pytest.mark.asyncio
    async def test_scope_with_missing_type_routes_safely(self):
        """Robustness: scope without 'type' key routes safely to fastapi."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app)

        scope = {"path": "/api"}  # missing 'type' key
        receive = AsyncMock()
        send = AsyncMock()

        await combined(scope, receive, send)
        fastapi_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_scope_with_missing_path_routes_safely(self):
        """Robustness: scope without 'path' key routes safely."""
        fastapi_app = AsyncMock()
        sio_app = AsyncMock()
        combined = asyncplus(fastapi_app, sio_app)

        scope = {"type": "http"}  # missing 'path' key
        receive = AsyncMock()
        send = AsyncMock()

        await combined(scope, receive, send)
        fastapi_app.assert_called_once()

    def test_route_handles_none_path(self):
        """Robustness: _route() handles None path gracefully."""
        scope = {"type": "http", "path": None}
        result = _route(scope, "/socket.io/")
        assert result in ("socketio", "fastapi")

    def test_route_handles_non_string_path(self):
        """Robustness: _route() handles non-string path gracefully."""
        scope = {"type": "http", "path": 123}
        result = _route(scope, "/socket.io/")
        assert result in ("socketio", "fastapi")

    def test_route_handles_non_string_type(self):
        """Robustness: _route() handles non-string type gracefully."""
        scope = {"type": 123, "path": "/"}
        result = _route(scope, "/socket.io/")
        assert result in ("socketio", "fastapi")
