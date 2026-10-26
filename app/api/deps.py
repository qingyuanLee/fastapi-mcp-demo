"""业务接口内部 JWT 校验依赖（MCP 工具 → ASGITransport 内部调用时解析内部 JWT 获取用户）"""

import jwt
from fastapi import HTTPException, Request

from app.config import settings


async def get_internal_user(request: Request) -> str:
    """解析调用方用户：
    - 优先内部 JWT（aud=feature-platform-api）：MCP 工具 → ASGITransport 内部调用
    - 其次业务 JWT：外部业务 API 调用（主应用中间件已校验签名/用户有效性）
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header.removeprefix("Bearer ")

    # 1) 内部 JWT（MCP 内部调用）
    try:
        payload = jwt.decode(
            token,
            settings.internal_jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="feature-platform-api",
        )
        return str(payload.get("sub"))
    except jwt.InvalidTokenError:
        pass

    # 2) 业务 JWT（外部业务 API 调用）
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return str(payload.get("sub"))
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
