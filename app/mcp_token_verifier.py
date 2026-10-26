"""FastMCP TokenVerifier（fastmcp 4.1.0 适配：子类必须调用 super().__init__）

业务 JWT 校验，与业务中间件的差异：
- 跳过 exp（过期时间）校验（verify_exp: False）——保留原设计
- 返回 FastMCP 的 AccessToken
"""

import jwt
from fastmcp.server.auth import AccessToken, TokenVerifier

from app.config import settings
from app.services.user import get_user_by_id


class BusinessTokenVerifier(TokenVerifier):
    def __init__(
        self,
        base_url: str | None = None,
        required_scopes: list[str] | None = None,
        resource_base_url: str | None = None,
    ):
        # fastmcp 4.1.0 必备：required_scopes / base_url / resource_base_url 由父类
        # AuthProvider.__init__ 在实例上初始化；缺失则运行期 AttributeError
        super().__init__(
            base_url=base_url,
            required_scopes=required_scopes,
            resource_base_url=resource_base_url,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
                options={
                    "verify_exp": False,  # ✅ 跳过过期校验（保留原设计）
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
        except jwt.InvalidTokenError:
            return None

        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            return None
        user = await get_user_by_id(user_id)
        if not user or not user.get("is_active"):
            return None

        return AccessToken(
            token=token,
            client_id=str(user_id),
            scopes=payload.get("scopes", []),
            expires_at=None,  # 不设置过期时间
            claims=payload,
        )
