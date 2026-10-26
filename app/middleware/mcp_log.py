"""MCP 调用日志增强中间件（纯 ASGI）。

问题背景：MCP 协议所有请求 URL 都是 /mcp/，普通访问日志只能看到"调用了 mcp"，
看不到具体调用了哪个工具。工具名藏在 JSON-RPC body 里：
    tools/call  → params.name
    initialize / tools/list  → method

本中间件对 /mcp/ 的 POST 请求读取并解析 body（读取后重新放回，下游可正常读取），
在响应开始时输出增强日志。GET（SSE 长连接）不读取 body，直接透传。

兼容性：纯 ASGI 实现，不缓冲响应 body，不影响 MCP streamable-http SSE 长连接
（Starlette 1.x 的 BaseHTTPMiddleware 会缓冲响应 body 与 SSE 冲突，不可用）。
"""

import json
import time
from urllib.parse import unquote

from starlette.types import ASGIApp, Message, Receive, Scope, Send


def _parse_mcp_rpc(body: bytes) -> tuple[str | None, str | None]:
    """解析 JSON-RPC body → (method, 工具名)。失败返回 (None, None)。"""
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return None, None
    if not isinstance(data, dict):
        return None, None
    rpc_method = data.get("method")
    if not isinstance(rpc_method, str):
        rpc_method = str(data.get("type"))  # notifications 消息兜底
    params = data.get("params")
    tool_name = None
    if isinstance(params, dict):
        tool_name = params.get("name")
        if not isinstance(tool_name, str):
            tool_name = None
    return rpc_method, tool_name


async def _drain_body(receive: Receive) -> bytes:
    """读取完整请求体（直到 more_body=False）。"""
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] == "http.request":
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        elif message["type"] == "http.disconnect":
            break
    return b"".join(chunks)


class McpAccessLogMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        method = scope.get("method", "")
        path = scope.get("path", "")
        client = scope.get("client") or ("", 0)
        client_host = client[0] if isinstance(client, (tuple, list)) else ""

        # 仅对 /mcp/ 的 POST 请求读取 body 解析工具名（GET 为 SSE 长连接，不读）
        rpc_method = tool_name = None
        body_chunks: list[bytes] = []
        receive_for_app = receive
        if method == "POST" and path.startswith("/mcp"):
            # 缓存 + 原样转发：不能吞掉消息，也不能编造 http.disconnect——
            # 否则下游（fastmcp/mcp handler）读 body 后再次 receive() 会误判客户端断开，
            # 导致 SSE 响应被中断（uvicorn: ASGI callable returned without completing response）。
            async def receive_wrapper() -> Message:
                message = await receive()
                if message["type"] == "http.request":
                    body_chunks.append(message.get("body", b""))
                return message

            receive_for_app = receive_wrapper

        # 可选：从 Authorization 解析调用者身份（失败则显示 "-"）
        username = "-"
        headers = scope.get("headers") or []
        auth_header = None
        for k, v in headers:
            if k.lower() == b"authorization":
                auth_header = v.decode("latin-1")
                break
        if auth_header:
            try:
                import jwt as _jwt  # 验证项目用 pyjwt；老项目可替换为自封装工具

                token = auth_header.removeprefix("Bearer ").strip()
                payload = _jwt.decode(token, options={"verify_signature": False})
                username = payload.get("sub") or payload.get("username") or "-"
            except Exception:
                username = "-"

        # MCP 会话 ID（streamable-http 会话追踪）
        session_id = None
        for k, v in headers:
            if k.lower() == b"mcp-session-id":
                session_id = unquote(v.decode("latin-1"))
                break

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                elapsed = time.perf_counter() - start
                status = message.get("status", 0)
                if path.startswith("/mcp"):
                    # 响应开始时请求体通常已读完，从缓存中解析 JSON-RPC
                    rpc_method, tool_name = _parse_mcp_rpc(b"".join(body_chunks))
                    print(
                        f"[mcp-log] 请求IP:{client_host}, 用户:{username}, "
                        f"MCP方法:{rpc_method}, 工具:{tool_name}, "
                        f"会话:{session_id or '-'}, 响应code:{status}, "
                        f"响应时间:{elapsed:.3f}s",
                        flush=True,
                    )
                else:
                    print(
                        f"[access] {method} {path} -> {status} {elapsed:.3f}s",
                        flush=True,
                    )
            await send(message)

        await self.app(scope, receive_for_app, send_wrapper)
