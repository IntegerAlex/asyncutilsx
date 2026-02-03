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

    def __call__(self, route: Route, scope: Scope) -> None: """
Invoked with the selected Route and its ASGI scope.

Parameters:
    route (Route): The routing target chosen for the current request — either "socketio" or "fastapi".
    scope (Scope): The ASGI connection scope dictionary for the current request.
"""
...


def router(
    routes: Sequence[tuple[Callable[[Scope], bool], ASGI3Application]],
    default_app: ASGI3Application | None = None,
) -> ASGI3Application:
    """
    Builds an ASGI application that dispatches each incoming scope to the first app whose predicate returns true.
    
    Parameters:
        routes (Sequence[tuple[Callable[[Scope], bool], ASGI3Application]]): Sequence of (predicate, app) pairs where each predicate is called with the ASGI scope and, if it returns `True`, its corresponding app will handle the request.
        default_app (ASGI3Application | None): Optional application to call when no predicate matches; if `None` and no predicates match, a RuntimeError is raised.
    
    Returns:
        ASGI3Application: An ASGI application callable that routes incoming requests according to the provided predicates.
    """

    async def app(
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        """
        Dispatches an incoming ASGI request to the first matching route application or to a default application.
        
        Parameters:
            scope (Scope): The ASGI connection scope for the request.
            receive (ASGIReceiveCallable): Callable to receive ASGI events from the server.
            send (ASGISendCallable): Callable to send ASGI events to the server.
        
        Raises:
            TypeError: If `scope` is not a dict.
            RuntimeError: If no predicate matches the scope and no default application is provided.
        """
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
    Create a composed ASGI application that dispatches requests between a FastAPI app and a Socket.IO server.
    
    Parameters:
        fastapi_app (FastAPI): FastAPI application to handle HTTP and lifespan requests.
        socketio_server (AsyncServer): Socket.IO AsyncServer to handle WebSocket/Socket.IO requests.
    
    Returns:
        ASGI3Application: An ASGI application that routes incoming scopes to the Socket.IO server or the FastAPI app based on scope type and request path.
    """
    return asyncplus(fastapi_app, socketio_server)


def health_check_route() -> (
    tuple[Callable[[Scope], bool], ASGI3Application]
):
    """
    Provide a predicate and ASGI application that implement a plain-text "/health" HTTP endpoint.
    
    The predicate returns True when the incoming scope's "path" equals "/health". The ASGI application responds with HTTP 200 and a plain-text body "OK".
    
    Returns:
        tuple[Callable[[Scope], bool], ASGI3Application]: (predicate, app) pair for routing the "/health" endpoint.
    """

    async def health_app(
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        """
        Responds to an HTTP request with a plain-text "OK" body.
        
        Sends an HTTP 200 response with header `Content-Type: text/plain` and the body "OK".
        """
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
    Normalize a Socket.IO AsyncServer or an ASGI app into an ASGI application.
    
    Parameters:
        socketio_app (AsyncServer | ASGIApp): A Socket.IO AsyncServer instance or an ASGI application.
    
    Returns:
        ASGIApp: An ASGI application. If given an AsyncServer, returns an ASGIApp wrapper around it; otherwise returns the input unchanged.
    """
    if isinstance(socketio_app, AsyncServer):
        return ASGIApp(socketio_app)
    return socketio_app


def _validate_socketio_path(socketio_path: str) -> None:
    """
    Validate a Socket.IO mount path and raise if it contains disallowed characters.
    
    Parameters:
    	socketio_path (str): The Socket.IO path to validate. An empty string is allowed
    		and is treated as the default path.
    
    Raises:
    	ValueError: If `socketio_path` contains control characters (ASCII < 32), a space,
    		or a tab. The exception message includes the offending path.
    """
    if not socketio_path:
        return
    invalid_chars = [c for c in socketio_path if ord(c) < 32 or c in (" ", "\t")]
    if invalid_chars:
        raise ValueError(
            "socketio_path contains invalid characters. "
            f"Use a simple path like '/socket.io' (got: {socketio_path!r})"
        )


def _normalize_socketio_path(socketio_path: str) -> str:
    """
    Normalize a Socket.IO mount path into a safe, absolute ASGI path.
    
    Validates the provided path, then returns a normalized value:
    - If empty, returns "/socket.io/".
    - If missing a leading "/", prepends one.
    - Otherwise returns the path unchanged.
    
    Parameters:
        socketio_path (str): Candidate Socket.IO path (may be empty).
    
    Returns:
        str: Normalized Socket.IO path suitable for matching against request paths.
    
    Raises:
        ValueError: If `socketio_path` contains disallowed characters.
    """
    _validate_socketio_path(socketio_path)
    if not socketio_path:
        return "/socket.io/"
    if not socketio_path.startswith("/"):
        return f"/{socketio_path}"
    return socketio_path


def _matches_socketio_path(path: str, socketio_path: str) -> bool:
    # Match /path, /path/, /path/...; empty socketio_path -> "/" only.
    # socketio_path is pre-normalized (leading slash) by _normalize_socketio_path.
    """
    Determine whether a request path targets the configured Socket.IO path or any of its subpaths.
    
    Parameters:
        path (str): The incoming request path (e.g., "/socket.io/", "/socket.io/123").
        socketio_path (str): The configured Socket.IO path, expected to be normalized with a leading
            "/" (an empty value is treated as the root "/").
    
    Returns:
        bool: `True` if `path` exactly equals the normalized base socketio path or starts with the
        base followed by "/", `False` otherwise.
    """
    base = socketio_path.rstrip("/")
    if not base:
        base = "/"
    return path == base or path.startswith(f"{base}/")


def _route(scope: Scope, socketio_path: str) -> Route:
    """
    Selects which application ("socketio" or "fastapi") should handle the given ASGI scope.
    
    Determination:
    - If scope.type is "lifespan" -> routes to fastapi.
    - If scope.type is "websocket" -> routes to socketio.
    - If scope.type is "http" and the request path matches socketio_path -> routes to socketio.
    - Otherwise -> routes to fastapi.
    
    Parameters:
        scope (Scope): ASGI scope dictionary; missing or non-string fields are treated as absent.
        socketio_path (str): Configured Socket.IO base path used to decide http routing.
    
    Returns:
        Route: `"socketio"` when the scope targets the Socket.IO application, `"fastapi"` otherwise.
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
    Dispatches an incoming ASGI connection to either the Socket.IO ASGI app or the FastAPI app, applying an optional timeout and optional Socket.IO-to-FastAPI fallback.
    
    If `route` is "socketio", the Socket.IO ASGI app is invoked; if it completes successfully the function returns. If the Socket.IO invocation raises an exception and `socketio_fallback_on_error` is True, the FastAPI app is invoked and the function returns; otherwise the original exception is re-raised. When `timeout` is set to a positive number, the selected ASGI invocation is bounded by that timeout; on timeout an asyncio.TimeoutError is raised after logging a warning.
    
    Parameters:
        route (Route): Target route decision, either "socketio" or "fastapi".
        scope (Scope): ASGI connection scope (not mutated).
        receive (ASGIReceiveCallable): ASGI receive callable (passed through).
        send (ASGISendCallable): ASGI send callable (passed through).
        socketio_asgi (ASGIApp): ASGI application for Socket.IO.
        fastapi_app (FastAPI): FastAPI ASGI application.
        socketio_fallback_on_error (bool): If True, fall back to FastAPI when the Socket.IO handler raises an exception.
        timeout (float | None): Optional per-call timeout in seconds; if None or non-positive, no timeout is applied.
    
    Returns:
        None
    """

    async def run_socketio() -> None:
        """
        Invoke the Socket.IO ASGI application using the current ASGI scope and I/O callables.
        
        Await the Socket.IO application's completion before returning.
        """
        await socketio_asgi(scope, receive, send)

    async def run_fastapi() -> None:
        """
        Invoke the FastAPI ASGI application with the current ASGI scope and I/O callables.
        """
        await fastapi_app(scope, receive, send)

    async def run_with_timeout(coro) -> None:
        """
        Execute the given coroutine honoring the outer `timeout` configuration.
        
        Parameters:
            coro: The awaitable to run.
        
        Returns:
            None
        
        Raises:
            asyncio.TimeoutError: If `timeout` is set to a value greater than zero and the coroutine does not complete within that many seconds.
        """
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
) -> ASGI3Application: """
    Create a composed ASGI application that routes incoming ASGI connections between a FastAPI app and a Socket.IO app.
    
    Parameters:
        fastapi_app (FastAPI): The FastAPI application that will handle HTTP requests and lifespan events.
        socketio_app (AsyncServer | ASGIApp): A python-socketio AsyncServer or any ASGI application that will handle WebSocket connections and Socket.IO HTTP endpoints.
    
    Returns:
        ASGI3Application: An ASGI application that delegates WebSocket and Socket.IO-path requests to the Socket.IO app and all other HTTP/lifespan requests to the FastAPI app, using the module's default routing conventions.
    """
    ...


@overload
def asyncplus(
    fastapi_app: FastAPI,
    socketio_app: AsyncServer | ASGIApp,
    *,
    socketio_path: str = "/socket.io/",
    debug_hook: DebugHook | None = None,
    socketio_fallback_on_error: bool = False,
    timeout: float | None = None,
) -> ASGI3Application: """
    Compose a single ASGI application that routes requests between a FastAPI app and a Socket.IO AsyncServer.
    
    Parameters:
        fastapi_app (FastAPI): The FastAPI application to handle HTTP and lifespan requests.
        socketio_app (AsyncServer | ASGIApp): A python-socketio AsyncServer or an ASGI application that should handle Socket.IO websocket/http paths.
        socketio_path (str): The Socket.IO mount path; validated and normalized before use (e.g., "/socket.io/").
        debug_hook (DebugHook | None): Optional callback invoked with the chosen route and request scope for debugging.
        socketio_fallback_on_error (bool): If True, fall back to the FastAPI app when handling via Socket.IO raises an exception.
        timeout (float | None): Optional per-request timeout in seconds applied to the delegated app; if None, no timeout is enforced.
    
    Returns:
        ASGI3Application: An ASGI application that inspects each scope, chooses the appropriate backend ("socketio" or "fastapi"), optionally invokes the debug_hook, and dispatches the request to the selected app with the configured fallback and timeout behavior.
    """
    ...


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
    Compose a FastAPI application and a Socket.IO application into a single ASGI app that routes requests to the appropriate backend.
    
    Parameters:
        socketio_path (str): Socket.IO mount path; empty string becomes "/socket.io/". Path is validated and may be normalized (leading slash added if missing).
        debug_hook (DebugHook | None): Optional callback invoked with the chosen route and ASGI scope for each request.
        socketio_fallback_on_error (bool): If true, a runtime error while dispatching to the Socket.IO app will cause the request to be retried against the FastAPI app.
        timeout (float | None): Per-request timeout in seconds for dispatching to the selected app; `None` disables timeouts.
    
    Raises:
        ValueError: If `socketio_path` contains invalid characters.
        TypeError: If an ASGI scope that is not a dict is passed to the returned application.
    
    Returns:
        ASGI3Application: An ASGI application that inspects each scope, chooses between the Socket.IO and FastAPI handlers, optionally invokes `debug_hook`, and dispatches with the configured fallback and timeout behavior.
    """
    socketio_asgi = _to_asgi_app(socketio_app)
    normalized_socketio_path = _normalize_socketio_path(socketio_path)

    async def asgi_app(
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        """
        Route an incoming ASGI connection to either the configured FastAPI app or the Socket.IO ASGI app based on the provided scope and module configuration.
        
        Parameters:
            scope (Scope): ASGI connection scope dictionary.
            receive (ASGIReceiveCallable): ASGI receive callable.
            send (ASGISendCallable): ASGI send callable.
        
        Raises:
            TypeError: If `scope` is not a dict.
        """
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