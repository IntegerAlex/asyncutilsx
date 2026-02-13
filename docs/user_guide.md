# asyncutilsx User Guide

Common patterns and usage for combining FastAPI and Socket.IO with **asyncplus**, **create_app**, **router**, and **health_check_route**.

---

## Basic setup (plug and play)

One ASGI app for your server; no mount path, same origin for API and Socket.IO.

**Simplest:** use `create_app(app, sio)` for the two-argument case.

```python
from fastapi import FastAPI
from socketio import AsyncServer
from asyncutilsx import create_app

app = FastAPI()
sio = AsyncServer(async_mode="asgi")

@sio.event
async def connect(sid, environ):
    print("connect", sid)

asgi_app = create_app(app, sio)
# Run: uvicorn asgi:asgi_app
```

Or use `asyncplus(app, sio)` directly (same result).

- HTTP (except `/socket.io/*`) → FastAPI  
- HTTP `/socket.io/*` → Socket.IO (polling)  
- WebSocket → Socket.IO  

---

## Custom Socket.IO path

When your Socket.IO server uses a path other than `/socket.io/`, pass it so routing matches:

```python
sio = AsyncServer(async_mode="asgi")  # or ASGIApp(sio, socketio_path="custom")
asgi_app = asyncplus(app, sio, socketio_path="/custom/")
```

`socketio_path` must not contain spaces or control characters (validated at call time).

---

## Debug hook (trace routing)

Inspect which route was chosen for each request without monkey-patching:

```python
def log_route(route: str, scope: dict) -> None:
    print(scope.get("type"), scope.get("path"), "->", route)

asgi_app = asyncplus(app, sio, debug_hook=log_route)
```

Use `logging.getLogger(__name__).info(...)` in production instead of `print` if you prefer.

---

## Socket.IO fallback on error

If Socket.IO rejects a connection (e.g. invalid handshake), you can fall back to FastAPI instead of surfacing an error:

```python
asgi_app = asyncplus(
    app,
    sio,
    socketio_fallback_on_error=True,
)
```

When `True`, a failed Socket.IO call is logged and the request is handed to FastAPI. Default is `False` (re-raise).

---

## Timeout (optional circuit breaker)

Limit how long each ASGI call (FastAPI or Socket.IO) can run; avoid hung requests:

```python
asgi_app = asyncplus(app, sio, timeout=30.0)
```

If the underlying app does not finish within 30 seconds, `asyncio.TimeoutError` is logged and re-raised. Use `timeout=None` (default) for no limit.

---

## Custom routing with `router()`

For more than FastAPI + Socket.IO (e.g. SSE, gRPC, or custom rules), use the pure **router** function. Pass a sequence of `(predicate, app)`; first match wins. Optionally provide a default app when no predicate matches.

```python
from asyncutilsx import router

# Predicate: scope["type"] == "websocket" -> Socket.IO; else FastAPI
routes = [
    (lambda s: s.get("type") == "websocket", socketio_asgi_app),
]
asgi_app = router(routes, default_app=fastapi_app)
```

Example: route by path prefix and type:

```python
def is_socketio(scope):
    t = scope.get("type")
    p = (scope.get("path") or "").startswith("/socket.io")
    return t == "websocket" or (t == "http" and p)

routes = [(is_socketio, socketio_asgi_app)]
asgi_app = router(routes, default_app=fastapi_app)
```

---

## Combining options

You can combine optional arguments in one call:

```python
asgi_app = asyncplus(
    app,
    sio,
    socketio_path="/custom/",
    debug_hook=log_route,
    socketio_fallback_on_error=True,
    timeout=60.0,
)
```

---

## Health check (production)

Use **health_check_route()** with **router()** to add a `/health` endpoint:

```python
from asyncutilsx import router, health_check_route

routes = [health_check_route(), (is_socketio, sio_app)]
asgi_app = router(routes, default_app=fastapi_app)
```

---

## Summary

| Need | Use |
|------|-----|
| Simplest two-argument setup | `create_app(app, sio)` |
| Single app, optional kwargs | `asyncplus(app, sio, ...)` |
| Custom Socket.IO path | `socketio_path="/custom/"` |
| Trace routing | `debug_hook=your_callback` |
| Fallback on Socket.IO error | `socketio_fallback_on_error=True` |
| Fail fast on hung requests | `timeout=30.0` |
| /health endpoint | `health_check_route()` + `router()` |
| Custom routing (SSE, gRPC, etc.) | `router(routes, default_app=...)` |
