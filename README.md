# fastapi_mcp —— 方案一（RemoteAuthProvider 版）验证项目

在 **fastmcp 4.1.0 / fastapi 0.138.2 / httpx 0.28.1** 真实环境端到端验证 MCP 封装方案。

## 依赖

| 依赖 | 版本声明（uv PEP 621，caret 等价） | 实际解析 |
|---|---|---|
| fastmcp | `>=4.1.0,<5.0.0`（即 ^4.1.0） | 4.1.0 |
| fastapi | `>=0.138.2,<0.139.0`（即 ^0.138.2） | 0.138.2 |
| httpx | `>=0.28.1,<0.29.0`（即 ^0.28.1） | 0.28.1 |

注：fastmcp 4.x 内部依赖 **httpx2**（httpx 2.x 新包名，2.13.1），由 fastmcp 自动带入；
`ASGITransport` / `InternalJWTAuth` 均使用 `httpx2`。

## 启动

```powershell
cd fastapi_mcp
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 业务 API：`GET /health`、`POST /api/v1/...`（业务 JWT）
- MCP 端点：`POST /mcp/`（streamable-http，尾斜杠必须保留；MCP 客户端配置为 `<base>/mcp/`）

## 端到端验证结果（2026-10-13，真实 4.1.0 环境）

| # | 验证项 | 结果 |
|---|---|---|
| 1 | `BusinessTokenVerifier()` 实例化（required_scopes 由 `super().__init__` 初始化） | ✅ `required_scopes=[]` |
| 2 | `RemoteAuthProvider`（authorization_servers + base_url）构建 | ✅ |
| 3 | `/health` 公开访问 | ✅ 200 |
| 4 | `/mcp/` 无 token → 401 | ✅ |
| 5 | `/mcp/` initialize 带业务 JWT → 200，serverInfo `Feature Platform MCP 4.1.0` | ✅ |
| 6 | tools/list → 3 个工具（`query_entity_meta` / `query_realtime_feature` / `query_offline_feature`，tags=`mcp_public`） | ✅ |
| 7 | tools/call `query_realtime_feature` → 200，`user_id=u_demo_001`（内部 JWT 全链路） | ✅ |
| 8 | 业务 API 带业务 JWT → 200，响应头 `X-New-Access-Token`（续期） | ✅ |
| 9 | **机制差异**：过期 token → 业务 API 401（校验 exp）；`/mcp` 200（verify_exp=False，跳过） | ✅ |
| 10 | 错误签名 token → `/mcp` 401（签名仍严格校验） | ✅ |

## fastmcp 4.1.0 关键适配点（均为实测）

1. **`BusinessTokenVerifier` 必须调 `super().__init__()`**：`required_scopes` / `base_url` /
   `resource_base_url` 由 `AuthProvider.__init__` 在实例上赋值；缺失运行期
   `AttributeError: ... object has no attribute 'required_scopes'`。
2. **`from_fastapi` 无显式 `auth` 形参**，但 `**settings` 透传至 `FastMCP.__init__`；
   实测 `from_fastapi(..., auth=auth)` 生效（`mcp.auth == auth`）。
3. **`httpx_client_kwargs` 禁止传 `transport`**：`from_fastapi` 内部已设置
   `transport=httpx2.ASGITransport(app=app)`，再传会 `TypeError`。
4. **`include_tags` 已改名 `tags`**（加到所有组件，无白名单过滤；业务路由统一打
   `mcp_public` 标签达到等价效果）。
5. **`RemoteAuthProvider`**：`authorization_servers` 必填、`base_url` 必填（4.x 替代旧版
   `resource_server_url`）；两参数仅服务 OAuth 元数据与 audience 描述，实际认证走自定义
   `TokenVerifier`，与服务器 IP 无关。
6. **中间件必须用纯 ASGI**：MCP streamable-http 是 SSE 长连接，Starlette 1.x 的
   `BaseHTTPMiddleware` 会缓冲响应 body，实测报错
   `Attempted to exit a cancel scope / BrokenResourceError / No response returned`；
   本项目日志/限流/续期/lifespan 中间件全部为纯 ASGI 实现。
7. **惰性 lifespan**：主应用 lifespan 被原系统占用时不接管，由
   `app/middleware/mcp_lifespan.py` 在首个 `/mcp` 请求幂等进入 `mcp_app.lifespan`。
8. **读 body 必须"缓存 + 原样转发"**：日志中间件解析 `/mcp` 的 JSON-RPC body 时，
   不能吞掉消息、更不能编造 `http.disconnect`——否则下游误判客户端断开，
   SSE 响应被中断（uvicorn 报 `ASGI callable returned without completing response`，
   客户端报 `SSE stream ended without a response` / `incomplete chunked read`）。
   修复前曾误判为"官方客户端兼容差异"，实为本中间件 bug（2026-10-15 已修复并复测）。

## token 机制差异（用户锁定口径）

- 业务 JWT：校验 exp + 自动续期（响应头 `X-New-Access-Token`）。
- `/mcp` token：签名 + 用户有效性严格校验，**跳过 exp、不续期**（客户端自管生命周期）。

## 用户登录接口（2026-10-29）

`POST /api/v1/login` —— 仅用户名签发业务 JWT，返回 `access_token + user_id`。

```json
// 请求：username 兼容 user id 或 name
{"username": "u_demo_001"}
{"username": "demo"}

// 响应
{"access_token": "<业务JWT>", "token_type": "bearer", "user_id": "u_demo_001"}
```

- 凭据：内存用户表（`app/services/user.py`），按 id 优先、name 次之匹配；
  不存在 / 未激活 → 401。
- Token：HS256 + `settings.jwt_secret`，`sub=user_id`，exp=1 小时，
  与 `e2e_call.py` 签发方式一致，登录后可直接调业务 API 和 `/mcp`。
- 放行：`JwtAuthMiddleware` 将 `/api/v1/login` 加入匿名白名单（同 `/health`）。
- 不暴露 MCP：auth router 不打 `mcp_public` 标签，`mcp.enable(only=True)` 自动过滤，
  工具列表无 login（已实测）。

实现文件：`app/api/auth.py`（新建）、`app/middleware/auth.py`（放行）、`app/main.py`（挂载）。

## 验证脚本

| 脚本 | 说明 |
|---|---|
| `e2e_call.py` | initialize → tools/call → 业务 API 全链路（含内部 JWT 与续期头） |
| `diff_check.py` | 过期/错误签名 token 的机制差异验证 |
| `smoke.py` | ASGITransport 进程内冒烟（health / 401 / initialize） |

> 说明：mcp 2.3.0 官方 Python 客户端此前报 "SSE stream ended without a response"，
> 经排查根因为 `app/middleware/mcp_log.py` 的 receive 语义 bug（编造
> `http.disconnect` 导致下游误判断开），2026-10-15 已修复；修复后
> `fastmcp list` / `e2e_call.py` / 普通 POST 全链路均 200 正常。

## nginx 反向代理配置（生产部署）

MCP streamable-http 是 SSE 长连接 + 内存会话，nginx 配置不当会出现
404 / timed out / 会话打散。以下为实测可用的完整配置。

### 完整配置

```nginx
upstream ffs_test {
    # ★ 会话粘性：同一会话永远落同一台后端
    # initialize 时还没有 session id（为空），拼 $remote_addr 兜底
    hash $http_mcp_session_id$remote_addr;
    server backend1:8000;
    server backend2:8000;
    keepalive 16;
}

# 无尾斜杠，前缀匹配，同时通吃 /mcp 和 /mcp/
location /mcp {
    # ★ 关键：proxy_pass 末尾带 /mcp/
    #   客户端发 /mcp（无尾斜杠）→ nginx 转成 /mcp/ 再转发
    #   客户端发 /mcp/（带尾斜杠）→ 原样转发
    #   不能让后端返回 307 重定向，否则 Location 是绝对 URL，
    #   客户端会绕过 nginx 直连后端，会话粘性失效
    proxy_pass http://ffs_test/mcp/;

    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # ★ 必须显式透传 Host，否则上游拿到 host=ffs_test 导致 URL 构造异常
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # SSE 必须关缓冲，否则事件被 nginx 攒着不发
    proxy_buffering off;
    proxy_cache off;

    # ★ SSE 长连接超时，防默认 60s 断流
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

### 客户端 URL 选择

| 客户端配置 | 是否可用 | 说明 |
|---|---|---|
| `http://{nginx}/mcp` | ✅ | nginx 自动转成 `/mcp/`，推荐 |
| `http://{nginx}/mcp/` | ✅ | 原样转发，也可用 |

两种写法 nginx 层自动兼容，客户端任选其一即可。

### 配套服务端配置

```python
# main.py 创建 MCP 子应用时
mcp_app = mcp.http_app(
    path="/",
    # ★ 闲置 8 小时回收 session，覆盖一个工作日
    #   默认 1800s=30分钟，闲置后客户端拿旧 sid 会 404 / timed out
    session_idle_timeout=28800,
)
```

### 三个常见 404 对照

| 现象 | 根因 | 修法 |
|---|---|---|
| 每次调用都可能 404 | 多后端轮询打散会话 | `hash $http_mcp_session_id$remote_addr` |
| 闲置 30 分钟后再调 404 | session idle 回收 | `session_idle_timeout=28800` |
| 服务端重启后第一次连接 404 | 客户端带旧 sid 发 initialize | 部署 `McpInitializeSessionResetMiddleware` |

