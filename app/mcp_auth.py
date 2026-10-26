"""FastMCP RemoteAuthProvider（fastmcp 4.1.0 签名适配）

- authorization_servers：必填（list[AnyHttpUrl]）
- base_url：资源服务器 URL（4.x 替代旧版 resource_server_url，必填）
"""

from fastmcp.server.auth import RemoteAuthProvider

from app.config import settings
from app.mcp_token_verifier import BusinessTokenVerifier

auth = RemoteAuthProvider(
    token_verifier=BusinessTokenVerifier(),
    authorization_servers=settings.mcp_authorization_servers,
    base_url=settings.mcp_resource_server_url,
)
