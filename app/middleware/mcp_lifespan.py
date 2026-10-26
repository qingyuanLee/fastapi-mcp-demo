"""MCP lifespan 惰性驱动中间件（纯 ASGI，SSE 兼容；零侵入主应用 lifespan）

首个 /mcp 请求幂等进入 mcp_app.lifespan 并保持到进程结束。
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from app.mcp_runtime import ensure_mcp_started


class McpLifespanMiddleware:
    def __init__(self, app: ASGIApp, mcp_app):
        self.app = app
        self.mcp_app = mcp_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http" and scope["path"].startswith("/mcp"):
            await ensure_mcp_started(self.mcp_app)
        await self.app(scope, receive, send)
