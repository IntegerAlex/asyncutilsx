# SPDX-License-Identifier: LGPL-2.1-only
# Copyright (c) 2025 Akshat kotpalliwar (alias IntegerAlex)

"""
ASGI wrapper for combining FastAPI and Socket.IO applications.

Designed around functional principles:
- Pure core: routing decision is a pure, total function (same scope → same route).
- Isolated effects: I/O (ASGI call) happens only at the boundary in one place.
- Immutable: scope and captured values are never mutated.
- Composition: asyncutilsx composes _to_asgi_app and a closure over _route + dispatch.
"""

from collections.abc import Callable
from typing import Any, Literal

from fastapi import FastAPI
from socketio.asgi import ASGIApp
from socketio.async_server import AsyncServer

__version__ = "0.1.0"
__all__ = ["asyncplus"]

# Type for routing decision only. Keeps invalid routes unrepresentable.
Route = Literal["socketio", "fastapi"]


def _to_asgi_app(socketio_app: AsyncServer | ASGIApp) -> ASGIApp:
    """
    Pure function. Same input → same output; no side effects.
    Referentially transparent: replaceable by its return value.
    """
    if isinstance(socketio_app, AsyncServer):
        return ASGIApp(socketio_app)
    return socketio_app


def _route(scope: dict[str, Any] | None) -> Route:
    """
    Pure, total function. Decides target from scope only.

    - Same scope → same Route; no side effects; does not mutate scope.
    - Total: handles None, non-dict, missing keys, non-string type/path
      without raising. Unknown scope types default to fastapi.
    """
    if scope is None or not isinstance(scope, dict):
        return "fastapi"
    raw_type = scope.get("type", "http")
    raw_path = scope.get("path", "")
    scope_type = raw_type if isinstance(raw_type, str) else "http"
    path = raw_path if isinstance(raw_path, str) else ""
    if scope_type == "websocket":
        return "socketio"
    if scope_type == "http" and path.startswith("/socket.io/"):
        return "socketio"
    return "fastapi"


async def _dispatch(
    route: Route,
    scope: dict[str, Any],
    receive: Callable[..., Any],
    send: Callable[..., Any],
    socketio_asgi: ASGIApp,
    fastapi_app: FastAPI,
) -> None:
    """
    Effect boundary: single place where I/O (ASGI call) happens.
    Does not mutate scope, receive, or send; only passes them through.
    """
    app: ASGIApp | FastAPI = socketio_asgi if route == "socketio" else fastapi_app
    await app(scope, receive, send)


def asyncplus(
    fastapi_app: FastAPI,
    socketio_app: AsyncServer | ASGIApp,
) -> Callable[..., Any]:
    """
    Pure function. Same (fastapi_app, socketio_app) → same returned ASGI app.

    No side effects; referentially transparent at call time.
    Builds the app by composition: _to_asgi_app then a closure that
    uses pure _route(scope) and a single _dispatch effect.
    """
    socketio_asgi = _to_asgi_app(socketio_app)

    async def asgi_app(
        scope: dict[str, Any] | None,
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        normalized_scope = scope if isinstance(scope, dict) else {}
        route = _route(normalized_scope)
        await _dispatch(
            route, normalized_scope, receive, send, socketio_asgi, fastapi_app
        )

    return asgi_app
