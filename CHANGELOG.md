# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-02-13

### Added

- **Configurable Socket.IO path**: `socketio_path="/custom/"` so routing matches custom paths (e.g. `ASGIApp(sio, socketio_path="custom")`).
- **ASGI typing**: `asgiref` types (`ASGI3Application`, `Scope`, `ASGIReceiveCallable`, `ASGISendCallable`) for static checking and spec compliance.
- **Fail-fast scope validation**: Non-dict scope raises `TypeError` instead of normalizing to `{}` (ASGI spec).
- **Debug hook**: Optional `debug_hook(route, scope)` callback to trace routing without monkey-patching.
- **Socket.IO fallback on error**: `socketio_fallback_on_error=True` falls back to FastAPI when Socket.IO rejects a connection; logs at INFO when falling back, WARNING when re-raising.
- **Explicit lifespan support**: Lifespan scope type explicitly routed to FastAPI in `_route`.
- **Timeout / circuit breaker**: Optional `timeout` (seconds) per ASGI call; on timeout logs and raises `asyncio.TimeoutError`.
- **`router(routes, default_app)`**: Pure function for custom routing (SSE, gRPC, etc.); takes `Sequence` of `(predicate, app)` pairs.
- **`create_app(fastapi_app, socketio_server)`**: Convenience for the two-argument case.
- **`health_check_route()`**: Returns `(predicate, app)` for `/health`; use with `router()`.
- **`DebugHook` Protocol**: Type-safe `debug_hook` parameter.
- **Overloads for `asyncplus`**: Two-argument and full keyword-only overloads for better IDE/type-checker support.
- **Property-based tests**: Hypothesis tests for `_route` (determinism, range, no mutation).
- **User guide**: [docs/user_guide.md](docs/user_guide.md) with common patterns; README “Why asyncplus() / asyncutilsx?” with mount vs asyncplus scenario.

### Changed

- **FP refactor**: Removed `Router` class and `ImmutableScope`; `router()` is a pure function; `_route(scope, socketio_path)` takes `Scope` directly.
- **Friendlier error messages**: `socketio_path` validation now suggests “Use a simple path like '/socket.io'” instead of raw “must not contain” message.
- **Module docstring**: Quickstart example and pointer to `create_app` and `router` (advanced).

### Fixed

- **Syntax errors in docstrings**: Fixed invalid Python syntax where docstrings were placed on the same line as function signatures in `DebugHook.__call__` and `asyncplus` overloads (would prevent module import).
- **Websocket routing**: Gate websocket routing by path matching (same as HTTP) instead of unconditionally routing all websockets to Socket.IO, preventing interception of non-Socket.IO WebSocket endpoints.
- **Path matching bug**: Fixed `_matches_socketio_path` handling of root path "/" which caused incorrect matching; now rejects "/" in validation with clear error message.

### Removed

- `Router` class (replaced by `router()` function).
- `ImmutableScope` and `ReadOnlyScope` (scope passed as dict; immutability by convention).

## [0.1.0] - 2025-01-31

### Added

- Initial release.
- Package `asyncutilsx`: ASGI wrapper `asyncplus(fastapi_app, socketio_app)` for combining FastAPI and Socket.IO in one app.
- Pure routing: HTTP (except `/socket.io/*`) → FastAPI; HTTP `/socket.io/*` and WebSocket → Socket.IO.
- Support for `AsyncServer` or pre-wrapped `ASGIApp` as the Socket.IO argument.
- Total handling of scope: `None` and non-dict scope normalized before dispatch; no unhandled exceptions from routing.

[Unreleased]: https://github.com/IntegerAlex/asyncplus/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/IntegerAlex/asyncplus/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/IntegerAlex/asyncplus/releases/tag/v0.1.0
