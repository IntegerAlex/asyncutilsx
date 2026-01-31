# asyncutilsx

ASGI wrapper for combining **FastAPI** and **Socket.IO** in one app.

**Author:** Akshat kotpalliwar (alias IntegerAlex)  
**SPDX-License-Identifier:** LGPL-2.1-only

Minimal and pure: one function, no side effects.

## Install

```bash
pip install asyncutilsx
```

## Usage

```python
from fastapi import FastAPI
from socketio import AsyncServer
from asyncutilsx import asyncplus

app = FastAPI()
sio = AsyncServer(async_mode="asgi")

@sio.event
async def connect(sid, environ):
    print("connect", sid)

asgi_app = asyncplus(app, sio)
# Run with: uvicorn asgi:asgi_app
```

- **HTTP** (except `/socket.io/*`) → FastAPI  
- **HTTP** `/socket.io/*` → Socket.IO (polling)  
- **WebSocket** → Socket.IO  

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

LGPL-2.1-only
