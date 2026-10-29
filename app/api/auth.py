"""用户登录接口（验证项目）：仅用户名签发业务 JWT，返回 access_token + user_id。

与现有 token 机制完全同构：
- 业务 JWT：HS256 + settings.jwt_secret，sub=user_id，exp=1 小时
- 与 e2e_call.py 的签发方式一致，登录后 token 可直接调用业务 API 与 /mcp
- 不声明 mcp_public 标签 → mcp.enable(only=True) 不会将其暴露为 MCP 工具
"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.user import _USERS

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名（user id 或 name）")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


def _find_user(username: str):
    """按 id 优先、name 次之查找内存用户表；返回 (user_id, user) 或 None"""
    user = _USERS.get(username)
    if user:
        return username, user
    for uid, u in _USERS.items():
        if u.get("name") == username:
            return uid, u
    return None


@router.post("/login", summary="用户登录（仅用户名）")
async def login(req: LoginRequest) -> LoginResponse:
    found = _find_user(req.username.strip())
    if not found:
        raise HTTPException(status_code=401, detail="User not found")
    user_id, user = found
    if not user.get("is_active"):
        raise HTTPException(status_code=401, detail="User inactive")

    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    access_token = jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )
    return LoginResponse(access_token=access_token, user_id=user_id)
