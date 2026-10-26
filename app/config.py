from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Feature Platform Unified API + MCP"

    # 业务 JWT
    jwt_secret: str = "change-me-strong-secret"
    jwt_algorithm: str = "HS256"

    # 内部 JWT（MCP 工具调用业务接口时签发）
    internal_jwt_secret: str = "change-me-internal-secret"
    internal_jwt_ttl_seconds: int = 60

    # MCP 对外地址（由部署方提供，不探测本机 IP）
    mcp_public_base_url: str = "https://feature-platform.internal"
    mcp_authorization_servers: list[str] = ["https://auth.feature-platform.internal"]

    @property
    def mcp_resource_server_url(self) -> str:
        """fastmcp 4.x RemoteAuthProvider 的 base_url（资源服务器 URL）"""
        return f"{self.mcp_public_base_url}/mcp"


settings = Settings()
