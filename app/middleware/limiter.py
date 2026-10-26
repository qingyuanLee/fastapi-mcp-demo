"""固定窗口限流中间件（纯 ASGI，SSE 兼容；验证项目简化实现）"""

import time
from collections import defaultdict

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: int = 100, window: int = 60):
        self.app = app
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        key = client[0] if client else "unknown"
        now = time.monotonic()
        self._hits[key] = [t for t in self._hits[key] if now - t < self.window]
        if len(self._hits[key]) >= self.limit:
            body = b'{"detail":"rate limit exceeded"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        self._hits[key].append(now)
        await self.app(scope, receive, send)
