"""业务 JWT 校验中间件（/mcp 放行：MCP 认证由 FastMCP 层 RemoteAuthProvider 负责）"""

import jwt
from starlette.authentication import (
    AuthenticationBackend,
    AuthenticationError,
    AuthCredentials,
)
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from app.config import settings
from app.services.user import get_user_by_id


class JwtAuthMiddleware(AuthenticationBackend):
    async def authenticate(self, conn: HTTPConnection):
        # 公开路径：健康检查
        if conn.url.path == "/health":
            return AuthCredentials(["anonymous"]), {"id": "anonymous"}
        # 公开路径：登录接口（无 token 匿名访问，凭据校验在接口内完成）
        if conn.url.path.startswith("/api/v1/login"):
            return AuthCredentials(["anonymous"]), {"id": "anonymous"}
        # 方案一：/mcp 放行业务认证（MCP 层自行校验业务 JWT，verify_exp: False）
        if conn.url.path.startswith("/mcp"):
            return AuthCredentials(["authenticated"]), {"id": "mcp"}

        auth_header = conn.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise AuthenticationError("Missing token")
        token = auth_header.removeprefix("Bearer ")
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired")
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token")

        user = await get_user_by_id(payload.get("sub"))
        if not user or not user.get("is_active"):
            raise AuthenticationError("User not found or inactive")
        return AuthCredentials(["authenticated"]), user

    @staticmethod
    def auth_exception_handler(conn: HTTPConnection, exc):
        return JSONResponse({"detail": str(exc)}, status_code=401)
