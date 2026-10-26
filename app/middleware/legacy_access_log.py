"""基于老项目 AccessMiddleware 的兼容修正版（纯 ASGI 等价实现，实测用）

老项目原实现继承 BaseHTTPMiddleware。Starlette 1.x 下 BaseHTTPMiddleware 与
MCP streamable-http 的 SSE 长连接冲突（实测：initialize 正常，tools/call 报
ReadError + RuntimeError: Attempted to exit a cancel scope ...），因此改为
纯 ASGI 等价实现——类名 AccessMiddleware、日志字段与格式保持不变，注册方式不变。
"""

import json
import logging
from datetime import datetime, timezone

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("legacy_access")


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
        rpc_method = str(data.get("type"))
    params = data.get("params")
    tool_name = None
    if isinstance(params, dict):
        tool_name = params.get("name")
        if not isinstance(tool_name, str):
            tool_name = None
    return rpc_method, tool_name


def _build_url(scope: Scope) -> str:
    """等价于 request.url：scheme://host + path + query。"""
    scheme = scope.get("scheme", "http")
    host = "localhost"
    for k, v in scope.get("headers") or []:
        if k.lower() == b"host":
            host = v.decode("latin-1")
            break
    url = f"{scheme}://{host}{scope.get('path', '')}"
    query = scope.get("query_string", b"")
    if query:
        url += "?" + query.decode("latin-1")
    return url


class AccessMiddleware:
    """记录请求日志中间件（兼容修正版：/mcp 请求额外输出 JSON-RPC 方法/工具名）"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = datetime.now(timezone.utc)
        client = scope.get("client") or ("", 0)
        client_host = client[0] if isinstance(client, (tuple, list)) else ""
        method = scope.get("method", "")
        path = scope.get("path", "")
        url = _build_url(scope)

        # /mcp 的 POST：缓存 + 原样转发 body（不能吞消息、不能编造 http.disconnect）
        rpc_method = tool_name = None
        session_id = None
        body_chunks: list[bytes] = []
        receive_for_app = receive
        if method == "POST" and path.startswith("/mcp"):
            for k, v in scope.get("headers") or []:
                if k.lower() == b"mcp-session-id":
                    session_id = v.decode("latin-1")
                    break

            async def receive_wrapper() -> Message:
                message = await receive()
                if message["type"] == "http.request":
                    body_chunks.append(message.get("body", b""))
                return message

            receive_for_app = receive_wrapper

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                end_time = datetime.now(timezone.utc)
                # 等内层（AuthenticationMiddleware 等）执行完再取用户（等价 request.user）
                username = "_"
                try:
                    user = scope.get("user")
                    username = user.username if user is not None and hasattr(user, "username") else ""
                except Exception:
                    pass
                status = message.get("status", 0)
                if path.startswith("/mcp"):
                    rpc_method, tool_name = _parse_mcp_rpc(b"".join(body_chunks))
                    log.info(
                        f'请求IP:{client_host}, 用户:{username}, '
                        f'请求方法:{method}, 请求接口:{url}, '
                        f'MCP方法:{rpc_method or "-"}, 工具:{tool_name or "-"}, '
                        f'会话:{session_id or "-"}, 响应code:{status}, '
                        f'响应时间:{end_time - start_time}'
                    )
                else:
                    log.info(
                        f'请求IP:{client_host}, 用户:{username}, '
                        f'请求方法:{method}, 请求接口:{url}, '
                        f'响应code:{status}, 响应时间:{end_time - start_time}'
                    )
            await send(message)

        await self.app(scope, receive_for_app, send_wrapper)
