# asyncutilsx

[![CodSpeed](https://img.shields.io/endpoint?url=https://codspeed.io/badge.json)](https://codspeed.io/IntegerAlex/asyncutilsx?utm_source=badge)

ASGI wrapper for combining **FastAPI** and **Socket.IO** in one app.

**Author:** Akshat kotpalliwar (alias IntegerAlex)  
**SPDX-License-Identifier:** LGPL-2.1-only

Minimal and pure: one function, no side effects.

## Why asyncplus() / asyncutilsx?

**Scenario: real-time chat app with REST API**

```python
# ❌ With mount() — problematic
app = FastAPI()
app.mount("/socket.io", socket_app)
# - Auth middleware may break Socket.IO handshake
# - CORS middleware may interfere
# - Extra latency on every Socket.IO message

# ✅ With asyncplus — clean
asgi_app = asyncplus(app, sio)
# - Socket.IO gets raw ASGI requests
# - FastAPI gets HTTP requests
# - Each handles its own concerns
```

FastAPI’s `app.mount("/path", other_asgi)` works, but you must serve Socket.IO on a subpath and deal with that path everywhere (client, CORS, proxies). **asyncplus** gives you a **single ASGI app**: one entry point for the server (e.g. uvicorn), no mount path, same origin for API and Socket.IO. Plug and play—no middleware, no timeouts or circuit breakers added; you keep full control of the ASGI apps you pass in.

## Install

```bash
pip install asyncutilsx
```

## Usage

```python
from fastapi import FastAPI
from socketio import AsyncServer
from asyncutilsx import asyncplus, create_app

app = FastAPI()
sio = AsyncServer(async_mode="asgi")

@sio.event
async def connect(sid, environ):
    print("connect", sid)

asgi_app = asyncplus(app, sio)
# Run with: uvicorn asgi:asgi_app
```

Or use the convenience helper: `asgi_app = create_app(app, sio)`.

- **HTTP** (except `/socket.io/*`) → FastAPI  
- **HTTP** `/socket.io/*` → Socket.IO (polling)  
- **WebSocket** (path matching `socketio_path`) → Socket.IO; other WebSocket paths → FastAPI  

Optional: `asyncplus(app, sio, socketio_path="/custom/", debug_hook=..., socketio_fallback_on_error=False, timeout=30.0)`.

For custom routing (e.g. SSE, gRPC), use the pure `router(routes, default_app)` function: pass a sequence of `(predicate, app)` pairs; first match wins; `default_app` used when none match.

See [docs/user_guide.md](docs/user_guide.md) for common patterns and examples.  

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Benchmarks

Performance benchmarks are continuously monitored with [CodSpeed](https://codspeed.io/IntegerAlex/asyncutilsx). To run benchmarks locally:

```bash
pytest benchmarks/ --codspeed
```

### asyncplus vs FastAPI mount

The suite includes direct comparisons between **asyncplus** and the **FastAPI mount workaround** (`app.mount("/socket.io", socket_app)`) on the same scenarios:

| Scenario | What’s measured |
|--------|------------------|
| HTTP to FastAPI (`/`) | Full ASGI dispatch to your FastAPI app |
| HTTP to Socket.IO (`/socket.io/`) | Dispatch to the Socket.IO ASGI app |
| WebSocket to Socket.IO (`/socket.io/`) | Dispatch to Socket.IO for the WebSocket |
| App creation | Time to build the combined ASGI app |

Same scopes and mocks are used for both approaches so results are comparable. See `benchmarks/test_bench_asyncplus_vs_mount.py`.

## License

LGPL-2.1-only
