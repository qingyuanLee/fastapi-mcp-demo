"""机制差异验证：过期业务 JWT 下 /mcp 跳过 exp（可用）、业务 API 校验 exp（拒绝）"""

import asyncio
import datetime

import httpx2
import jwt

from app.config import settings


async def main():
    expired = jwt.encode(
        {
            "sub": "u_demo_001",
            "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    url = "http://127.0.0.1:8000"

    async with httpx2.AsyncClient(timeout=30) as client:
        # 1) 过期 token 调业务 API → 期望 401（exp 校验）
        async with client.stream(
            "POST", f"{url}/api/v1/realtime/feature/query",
            headers={"Authorization": f"Bearer {expired}"},
            json={"entity_type": "user", "entity_id": "u_1001", "feature_names": ["age"]},
        ) as r:
            b = await r.aread()
            print("业务 API 过期 token:", r.status_code, b.decode()[:120])

        # 2) 过期 token 调 /mcp initialize → 期望 200（verify_exp: False）
        async with client.stream(
            "POST", f"{url}/mcp/", headers={"Authorization": f"Bearer {expired}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "diff", "version": "1.0"}}},
        ) as r:
            b = await r.aread()
            body = b.decode()
            print("MCP 过期 token:", r.status_code, "| serverInfo 在响应中:", '"serverInfo"' in body)

        # 3) 错误签名 token 调 /mcp → 期望 401
        bad = jwt.encode({"sub": "u_demo_001"}, "wrong-secret", algorithm="HS256")
        async with client.stream(
            "POST", f"{url}/mcp/", headers={"Authorization": f"Bearer {bad}"},
            json={"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "diff", "version": "1.0"}}},
        ) as r:
            await r.aread()
            print("MCP 错误签名:", r.status_code)


asyncio.run(main())
