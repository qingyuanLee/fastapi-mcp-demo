"""MCP initialize 会话重置中间件（纯 ASGI）。

问题背景（服务端重启后第一次连接必现 404）：
  - streamable-http 的 session 是 uvicorn 进程内存态，服务端重启后全部清空
  - 客户端（Cherry Studio 等）会缓存上次的 Mcp-Session-Id
  - 重连时客户端带着旧 session-id 发 initialize，FastMCP 的 streamable_http_manager
    发现该 session 不存在，直接返回 404 "Session not found"（实测复现：
    initialize 带无效 session-id → HTTP 404；不带 → 200 新建）
  - 客户端收到 404 后再 fallback 不带 session 重新 initialize，所以"第一次报错、
    后面就正常"，且后续重启客户端都正常（直到下次服务端重启）

修复思路：
  initialize 的语义就是"建立新会话"，按协议本不应携带 Mcp-Session-Id。
  本中间件只在识别到 JSON-RPC method=initialize 时才剥离请求头里的 mcp-session-id，
  让 manager 按新会话处理；tools/call 等其他请求的 sid 原样保留。

实现要点（踩过的坑）：
  - 不能 drain body：drain 后 replay 会破坏 mcp_app 的 SSE 响应流
    （"ASGI callable returned without completing response" / 客户端 ReadTimeout）
  - 不能无条件 strip：正常 tools/call 依赖 sid，strip 后会 400
  - 只 peek 第一个 http.request body 块（initialize body 很小，一般一次发完），
    解析出 method=initialize 才 strip；消息原样透传，不缓存不破坏流
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class McpInitializeSessionResetMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")

        if method == "POST" and path.startswith("/mcp"):
            # peek 第一个请求块，判断是否 initialize
            first = await receive()
            if first.get("type") == "http.request":
                chunk = first.get("body", b"") or b""
                try:
                    data = json.loads(chunk.decode("utf-8"))
                    if isinstance(data, dict) and data.get("method") == "initialize":
                        headers = [h for h in (scope.get("headers") or [])
                                   if h[0].lower() != b"mcp-session-id"]
                        scope = {**scope, "headers": headers}
                except Exception:
                    pass  # body 分块/非 JSON，不 strip，保持原样

            # 把 peek 到的第一个块放回 receive 流，原样透传
            async def receive_wrapper() -> Message:
                nonlocal first
                if first is not None:
                    msg, first = first, None
                    return msg
                return await receive()

            await self.app(scope, receive_wrapper, send)
            return

        await self.app(scope, receive, send)
