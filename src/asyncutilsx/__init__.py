# SPDX-License-Identifier: LGPL-2.1-only
# Copyright (c) 2025 Akshat kotpalliwar (alias IntegerAlex)

"""
ASGI wrapper for combining FastAPI and Socket.IO applications.

Quickstart:
    from fastapi import FastAPI
    import socketio

    app = FastAPI()
    sio = socketio.AsyncServer(async_mode="asgi")

    asgi_app = asyncplus(app, sio)
    # Run with: uvicorn module:asgi_app

For the simplest two-argument call, use create_app(app, sio). For custom
routing (SSE, gRPC, etc.), use router(routes, default_app=...) (advanced).

Designed around functional principles:
- Pure core: routing decision is a pure, total function (same scope → same route).
- Isolated effects: I/O (ASGI call) happens only at the boundary in one place.
- Immutable: scope and captured values are never mutated.
- Composition: asyncutilsx composes _to_asgi_app and a closure over _route + dispatch.
"""

from collections.abc import Callable, Sequence
import asyncio
import logging
from typing import Literal, Protocol, overload

from asgiref.typing import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    Scope,
)
from fastapi import FastAPI
from socketio.asgi import ASGIApp
from socketio.async_server import AsyncServer

__version__ = "0.2.0"
__all__ = ["asyncplus", "create_app", "router", "DebugHook", "health_check_route"]

# Type for routing decision only. Keeps invalid routes unrepresentable.
# Literal type (no class), so __slots__ does not apply.
Route = Literal["socketio", "fastapi"]
_logger = logging.getLogger(__name__)


class DebugHook(Protocol):
    """Protocol for optional routing callback. Enables type-safe debug_hook."""

    def __call__(self, route: Route, scope: Scope) -> None: ...


def router(
    routes: Sequence[tuple[Callable[[Scope], bool], ASGI3Application]],
    default_app: ASGI3Application | None = None,
) -> ASGI3Application:
    """
    Pure function. Builds an ASGI app that dispatches by the first matching
    (predicate, app) in routes; if none match, uses default_app or raises.

    Example:
        routes = [(lambda s: s.get("type") == "websocket", ws_app)]
        app = router(routes, default_app=fastapi_app)
    """

    async def app(
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        if not isinstance(scope, dict):
            raise TypeError(
                f"ASGI scope must be dict, got {type(scope).__name__}"
            )
        for predicate, route_app in routes:
            if predicate(scope):
                await route_app(scope, receive, send)
                return
        if default_app is None:
            raise RuntimeError("No matching route and no default app")
        await default_app(scope, receive, send)

    return app


def create_app(
    fastapi_app: FastAPI,
    socketio_server: AsyncServer,
) -> ASGI3Application:
    """
    Simplest setup: pass your FastAPI and Socket.IO server.

    Example:
        app = FastAPI()
        sio = socketio.AsyncServer(async_mode="asgi")
        asgi_app = create_app(app, sio)
    """
    return asyncplus(fastapi_app, socketio_server)


def health_check_route() -> (
    tuple[Callable[[Scope], bool], ASGI3Application]
):
    """
    Returns a (predicate, app) tuple for a /health endpoint. Use with router().

    Example:
        routes = [health_check_route(), (is_socketio, sio_app)]
        app = router(routes, default_app=fastapi_app)
    """

    async def health_app(
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": b"OK",
        })

    return (lambda s: s.get("path") == "/health", health_app)


def _to_asgi_app(socketio_app: AsyncServer | ASGIApp) -> ASGIApp:
    """
    Pure function. Same input → same output; no side effects.
    Referentially transparent: replaceable by its return value.
    """
    if isinstance(socketio_app, AsyncServer):
        return ASGIApp(socketio_app)
    return socketio_app


def _validate_socketio_path(socketio_path: str) -> None:
    """Raise ValueError if path is invalid. Empty is allowed (normalized to default)."""
    if not socketio_path:
        return
    invalid_chars = [c for c in socketio_path if ord(c) < 32 or c in (" ", "\t")]
    if invalid_chars:
        raise ValueError(
            "socketio_path contains invalid characters. "
            f"Use a simple path like '/socket.io' (got: {socketio_path!r})"
        )


def _normalize_socketio_path(socketio_path: str) -> str:
    _validate_socketio_path(socketio_path)
    if not socketio_path:
        return "/socket.io/"
    if not socketio_path.startswith("/"):
        return f"/{socketio_path}"
    return socketio_path


def _matches_socketio_path(path: str, socketio_path: str) -> bool:
    # Match /path, /path/, /path/...; empty socketio_path -> "/" only.
    # socketio_path is pre-normalized (leading slash) by _normalize_socketio_path.
    base = socketio_path.rstrip("/")
    if not base:
        base = "/"
    return path == base or path.startswith(f"{base}/")


def _route(scope: Scope, socketio_path: str) -> Route:
    """
    Pure, total function. Decides target from scope only.

    - Same scope → same Route; no side effects; does not mutate scope.
    - Total over valid ASGI scope dicts; does not mutate scope.
      Unknown scope types default to fastapi.
    - ASGI does not guarantee "path" for all scope types (e.g. lifespan);
      we use scope.get("path", "") so missing path is safe.
    """
    raw_type = scope.get("type", "http")
    raw_path = scope.get("path", "")  # optional in ASGI for non-http/websocket
    scope_type = raw_type if isinstance(raw_type, str) else "http"
    path = raw_path if isinstance(raw_path, str) else ""
    if scope_type == "lifespan":
        return "fastapi"
    if scope_type == "websocket":
        return "socketio"
    if scope_type == "http" and _matches_socketio_path(path, socketio_path):
        return "socketio"
    return "fastapi"


async def _dispatch(
    route: Route,
    scope: Scope,
    receive: ASGIReceiveCallable,
    send: ASGISendCallable,
    socketio_asgi: ASGIApp,
    fastapi_app: FastAPI,
    *,
    socketio_fallback_on_error: bool,
    timeout: float | None = None,
) -> None:
    """
    Effect boundary: single place where I/O (ASGI call) happens.
    Does not mutate scope, receive, or send; only passes them through.
    If timeout is set, wraps the ASGI call in asyncio.wait_for; on timeout
    logs and raises asyncio.TimeoutError (optional circuit breaker).
    """

    async def run_socketio() -> None:
        await socketio_asgi(scope, receive, send)

    async def run_fastapi() -> None:
        await fastapi_app(scope, receive, send)

    async def run_with_timeout(coro) -> None:
        if timeout is not None and timeout > 0:
            try:
                await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                _logger.warning(
                    "ASGI call timed out after %s seconds (scope type=%s)",
                    timeout,
                    scope.get("type", "?"),
                )
                raise
        else:
            await coro

    if route == "socketio":
        try:
            await run_with_timeout(run_socketio())
        except asyncio.TimeoutError:
            raise
        except Exception as exc:
            if socketio_fallback_on_error:
                _logger.info(
                    "Socket.IO connection failed, falling back to FastAPI: %s",
                    exc,
                )
                await run_with_timeout(run_fastapi())
                return
            _logger.warning(
                "Socket.IO rejected connection: %s", exc, exc_info=True
            )
            raise
        return
    await run_with_timeout(run_fastapi())


@overload
def asyncplus(
    fastapi_app: FastAPI,
    socketio_app: AsyncServer | ASGIApp,
) -> ASGI3Application: ...


@overload
def asyncplus(
    fastapi_app: FastAPI,
    socketio_app: AsyncServer | ASGIApp,
    *,
    socketio_path: str = "/socket.io/",
    debug_hook: DebugHook | None = None,
    socketio_fallback_on_error: bool = False,
    timeout: float | None = None,
) -> ASGI3Application: ...


def asyncplus(
    fastapi_app: FastAPI,
    socketio_app: AsyncServer | ASGIApp,
    *,
    socketio_path: str = "/socket.io/",
    debug_hook: DebugHook | None = None,
    socketio_fallback_on_error: bool = False,
    timeout: float | None = None,  # seconds; None = no timeout
) -> ASGI3Application:
    """
    Pure function. Same (fastapi_app, socketio_app) → same returned ASGI app.

    No side effects; referentially transparent at call time.
    Builds the app by composition: _to_asgi_app then a closure that
    uses pure _route(scope) and a single _dispatch effect.

    Raises ValueError if socketio_path contains invalid characters.
    timeout: seconds per ASGI call; None = no timeout. On timeout,
    asyncio.TimeoutError is logged and re-raised (optional circuit breaker).
    """
    socketio_asgi = _to_asgi_app(socketio_app)
    normalized_socketio_path = _normalize_socketio_path(socketio_path)

    async def asgi_app(
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        if not isinstance(scope, dict):
            raise TypeError(
                f"ASGI scope must be dict, got {type(scope).__name__}"
            )
        route = _route(scope, normalized_socketio_path)
        if debug_hook is not None:
            debug_hook(route, scope)
        await _dispatch(
            route,
            scope,
            receive,
            send,
            socketio_asgi,
            fastapi_app,
            socketio_fallback_on_error=socketio_fallback_on_error,
            timeout=timeout,
        )

    return asgi_app
