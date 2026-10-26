"""MCP 工具内部调用业务接口时签发内部 JWT（协程范式 + fastmcp 4.x 用 httpx2）"""

from datetime import datetime, timedelta, timezone

import httpx2  # fastmcp 4.x 内部依赖 httpx2（httpx 2.x 新包名）
import jwt
from fastmcp.server.dependencies import get_access_token

from app.config import settings


class InternalJWTAuth(httpx2.Auth):
    """在 MCP 工具调用业务接口时签发内部 API JWT（异步协程范式）"""

    async def async_auth_flow(self, request):
        access_token = get_access_token()
        user_id = (access_token.claims.get("sub") if access_token else None) or "system"
        internal_token = jwt.encode(
            {
                "sub": user_id,
                "iss": "feature-platform-mcp",
                "aud": "feature-platform-api",
                "exp": datetime.now(timezone.utc)
                + timedelta(seconds=settings.internal_jwt_ttl_seconds),
            },
            settings.internal_jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        request.headers["Authorization"] = f"Bearer {internal_token}"
        yield request
