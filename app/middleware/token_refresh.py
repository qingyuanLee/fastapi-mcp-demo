"""业务 JWT 自动续期中间件（纯 ASGI，SSE 兼容；/mcp 放行不续期）"""

import jwt
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings


class TokenRefreshMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["path"].startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        new_token = None
        headers = dict(scope.get("headers") or [])
        raw_auth = headers.get(b"authorization", b"")
        if raw_auth.startswith(b"Bearer "):
            try:
                payload = jwt.decode(
                    raw_auth[7:].decode(),
                    settings.jwt_secret,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": True},
                )
                new_token = jwt.encode(
                    payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
                )
            except jwt.InvalidTokenError:
                pass

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and new_token:
                msg = message.copy()
                msg["headers"] = list(message.get("headers") or []) + [
                    (b"X-New-Access-Token", new_token.encode())
                ]
                await send(msg)
            else:
                await send(message)

        await self.app(scope, receive, send_wrapper)
