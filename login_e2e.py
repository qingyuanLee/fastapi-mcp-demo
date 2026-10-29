"""登录接口端到端验证：
1. POST /api/v1/login（id / name / 不存在用户）
2. 用登录 token 调业务 API（应 200）
3. 用登录 token 调 /mcp initialize + tools/list（应 200，且工具列表无 login）
4. e2e 既有链路仍正常
"""
import asyncio
import datetime
import json

import httpx2
import jwt

from app.config import settings

BASE = "http://127.0.0.1:8000"


def make_token():
    return jwt.encode(
        {
            "sub": "u_demo_001",
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


async def login(client, username):
    r = await client.post(
        f"{BASE}/api/v1/login", json={"username": username}, timeout=10
    )
    print(f"[login] username={username} → HTTP {r.status_code} body={r.text[:200]}")
    return r


async def main():
    async with httpx2.AsyncClient() as client:
        # 1) 登录：id、name、不存在用户
        r_id = await login(client, "u_demo_001")
        await login(client, "demo")
        r_bad = await login(client, "nobody")

        # 2) 用登录 token 调业务 API
        if r_id.status_code == 200:
            token = r_id.json()["access_token"]
            resp = await client.get(
                f"{BASE}/health",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            print(f"[health-with-login-token] HTTP {resp.status_code} body={resp.text[:80]}")

        # 3) 用登录 token 走 MCP initialize + tools/list
        if r_id.status_code == 200:
            token = r_id.json()["access_token"]
            init_body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "login-e2e", "version": "1"},
                },
            }
            async with client.stream(
                "POST",
                f"{BASE}/mcp/",
                json=init_body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
                timeout=10,
            ) as resp:
                sid = resp.headers.get("mcp-session-id", "-")
                text = await resp.aread()
                print(f"[mcp-initialize] HTTP {resp.status_code} sid={sid}")

            if sid != "-":
                list_body = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                }
                async with client.stream(
                    "POST",
                    f"{BASE}/mcp/",
                    json=list_body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Mcp-Session-Id": sid,
                        "Accept": "application/json, text/event-stream",
                        "Content-Type": "application/json",
                    },
                    timeout=10,
                ) as resp:
                    text = await resp.aread()
                    print(f"[mcp-tools-list] HTTP {resp.status_code}")
                    # 解析 SSE data 里的 JSON
                    for line in text.decode().splitlines():
                        if line.startswith("data:"):
                            data = json.loads(line[5:].strip())
                            tools = data.get("result", {}).get("tools", [])
                            names = [t["name"] for t in tools]
                            print(f"  tools={names}")
                            print(f"  login 是否暴露为工具: {'login' in names}")

        # 4) 对照：无 token 访问业务 API 应 401
        resp = await client.get(f"{BASE}/api/v1/meta/entity/meta", timeout=10)
        print(f"[no-token-business-api] HTTP {resp.status_code}（预期 401）")


asyncio.run(main())
