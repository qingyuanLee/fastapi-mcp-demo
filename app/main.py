"""主应用：业务路由 + 中间件 + MCP 挂载（fastmcp 4.1.0 适配版）"""

import httpx2  # fastmcp 4.x 内部依赖 httpx2（httpx 2.x 新包名）
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware
from starlette.middleware.authentication import AuthenticationMiddleware

from app.api.meta import router as meta_router
from app.api.offline import router as offline_router
from app.api.realtime import router as realtime_router
from app.api.legacy import router as legacy_router
from app.api.naming import router as naming_router
from app.internal_jwt import InternalJWTAuth
from app.mcp_auth import auth
from app.middleware.access_log import AccessLogMiddleware
from app.middleware.auth import JwtAuthMiddleware
from app.middleware.limiter import RateLimitMiddleware
from app.middleware.mcp_lifespan import McpLifespanMiddleware
from app.middleware.mcp_log import McpAccessLogMiddleware
from app.middleware.mcp_init_session_reset import McpInitializeSessionResetMiddleware
from app.middleware.token_refresh import TokenRefreshMiddleware

# 1. 存量业务 FastAPI 应用（仅作为路由源和内部调用目标）
#    generate_unique_id_function：自定义 operation_id 生成规则（注意：FastAPI 0.138.x
#    参数名是 generate_unique_id_function，旧版叫 generate_unique_id，传错会被静默忽略）——
#    FastAPI 默认生成 {函数名}_{路径}_{method}（如 query_naming_demo_api_v1_naming_demo_post），
#    OpenAPIProvider 会把该 operation_id 直接用作 MCP 工具名（split("__") 截不掉单下划线长名）。
#    这里改为纯函数名，MCP 工具名即为 {api_name}。
#    注意：显式指定 operation_id 的路由优先于该规则（routing.py:1006），不受影响。
def _short_generate_unique_id(route):
    return route.name  # FastAPI APIRoute.name 默认 = 端点函数名


business_app = FastAPI(
    title="Feature Platform Business API",
    generate_unique_id_function=_short_generate_unique_id,
)
business_app.include_router(meta_router, prefix="/api/v1")
business_app.include_router(realtime_router, prefix="/api/v1")
business_app.include_router(offline_router, prefix="/api/v1")
business_app.include_router(legacy_router, prefix="/api/v1")
business_app.include_router(naming_router, prefix="/api/v1")

# 2. 从业务应用生成 MCP 服务器，配置自定义 TokenVerifier
#    4.x 适配：
#    - from_fastapi 签名无显式 auth，但 **settings 会透传给 FastMCP.__init__(auth=...)，
#      实测 4.1.0 from_fastapi(..., auth=auth) 生效（mcp.auth == auth）
#    - 不要传 transport：from_fastapi 内部已设置 transport=ASGITransport(app=app)，
#      httpx_client_kwargs 再传 transport 会 TypeError（4.1.0 实测）
mcp = FastMCP.from_fastapi(
    app=business_app,
    name="Feature Platform MCP",
    # 注意：此处不要传 tags={"mcp_public"}！
    # from_fastapi 的 tags 是"给全部工具附加标签"（union 语义，非过滤），
    # 若传了会把 mcp_public 加到所有工具上，导致下方 enable(only=True) 匹配不到差异。
    # 标签应只在 FastAPI 路由/APIRouter 上声明（见 app/api/meta.py 等）。
    auth=auth,            # 经 **settings 透传 → FastMCP(auth=...)
    httpx_client_kwargs={
        "base_url": "http://internal",
        "auth": InternalJWTAuth(),
    },
)

# 4.x 关键：from_fastapi 的 tags 参数只是"给全部工具附加标签"，不是过滤！
# 要实现"只暴露声明了 mcp_public 的路由"，必须显式 allowlist：
#   only=True = 先禁用全部组件，再启用带 mcp_public tag 的组件
# 不加这行 → 所有业务接口都会作为 MCP 工具暴露（实测复现）
mcp.enable(tags={"mcp_public"}, only=True)

# 工具调用日志：fastmcp 官方 LoggingMiddleware
# - methods=["tools/call"]：只记录工具调用，过滤 initialize/list 噪音
# - include_payloads=True：payload 含工具名 + 入参
# - max_payload_length：截断超长入参，防日志爆炸
logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
mcp.add_middleware(
    LoggingMiddleware(
        methods=["tools/call"],
        include_payloads=True,
        max_payload_length=800,
    )
)

# 3. MCP ASGI 子应用（lifespan 由 mcp_runtime 惰性驱动，见 app/mcp_runtime.py）
#    session_idle_timeout：闲置多少秒后回收 session（默认 1800s=30分钟）
#    生产建议 28800s=8小时（覆盖一个工作日），避免闲置后客户端拿旧 sid 404
mcp_app = mcp.http_app(path="/", session_idle_timeout=28800)

# 4. 主 FastAPI 应用（lifespan 由原系统持有，本方案不接管）
app = FastAPI(title="Feature Platform Unified API + MCP")

# 5. 中间件注册（执行序从外到内）
#    关键：全部使用纯 ASGI 中间件——MCP streamable-http 是 SSE 长连接，
#    Starlette 1.x 的 BaseHTTPMiddleware 会缓冲响应 body，与 SSE 无限流冲突
#    （实测报错：Attempted to exit a cancel scope / BrokenResourceError / No response returned）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id", "WWW-Authenticate", "X-New-Access-Token"],
)
app.add_middleware(
    AuthenticationMiddleware,
    backend=JwtAuthMiddleware(),
    on_error=JwtAuthMiddleware.auth_exception_handler,
)
app.add_middleware(McpLifespanMiddleware, mcp_app=mcp_app)
app.add_middleware(TokenRefreshMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RateLimitMiddleware)
# MCP 调用日志增强（放最外层 = 最后 add）：解析 JSON-RPC body 显示具体工具名
app.add_middleware(McpAccessLogMiddleware)
# initialize 会话重置（最外层）：服务端重启后客户端带旧 session-id 发 initialize，
# 中间件剥离该头让 manager 新建会话，避免第一次连接 404 "Session not found"
app.add_middleware(McpInitializeSessionResetMiddleware)

# 7. 业务路由（对外业务 API，与 business_app 同源）
app.include_router(meta_router, prefix="/api/v1")
app.include_router(realtime_router, prefix="/api/v1")
app.include_router(offline_router, prefix="/api/v1")
app.include_router(legacy_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "healthy"}


# 8. 最后挂载 MCP 子应用
app.mount("/mcp", mcp_app)
