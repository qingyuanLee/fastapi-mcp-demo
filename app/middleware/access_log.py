"""访问日志中间件（纯 ASGI，不缓冲 body，兼容 SSE 流式响应）"""

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        method = scope.get("method", "")
        path = scope.get("path", "")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                elapsed = time.perf_counter() - start
                print(
                    f"[access] {method} {path} -> {message['status']} {elapsed:.3f}s",
                    flush=True,
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
