# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-31

### Added

- Initial release.
- Package `asyncutilsx`: ASGI wrapper `asyncplus(fastapi_app, socketio_app)` for combining FastAPI and Socket.IO in one app.
- Pure routing: HTTP (except `/socket.io/*`) → FastAPI; HTTP `/socket.io/*` and WebSocket → Socket.IO.
- Support for `AsyncServer` or pre-wrapped `ASGIApp` as the Socket.IO argument.
- Total handling of scope: `None` and non-dict scope normalized before dispatch; no unhandled exceptions from routing.

[Unreleased]: https://github.com/IntegerAlex/asyncplus/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/IntegerAlex/asyncplus/releases/tag/v0.1.0
