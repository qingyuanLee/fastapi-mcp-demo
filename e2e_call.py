"""完整端到端验证：initialize → tools/call（内部 JWT 链路 + 业务端点）"""

import asyncio
import datetime
import json

import httpx2
import jwt

from app.config import settings


async def main():
    token = jwt.encode(
        {
            "sub": "u_demo_001",
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    headers = {"Authorization": f"Bearer {token}"}
    url = "http://127.0.0.1:8000/mcp/"

    async with httpx2.AsyncClient(timeout=30) as client:
        # initialize
        async with client.stream(
            "POST", url, headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "e2e", "version": "1.0"}}},
        ) as r:
            session_id = r.headers.get("mcp-session-id")
            body = await r.aread()
            print("initialize:", r.status_code, "| session:", session_id[:8], "| serverInfo:", "Feature Platform MCP" in body.decode())

        # tools/call：query_realtime_feature
        call_body = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "query_realtime_feature",
                "arguments": {"entity_type": "user", "entity_id": "u_1001",
                              "feature_names": ["age", "city"]},
            },
        }
        async with client.stream(
            "POST", url, headers={**headers, "Mcp-Session-Id": session_id}, json=call_body
        ) as r:
            print("tools/call:", r.status_code)
            body = await r.aread()
            print("tools/call body:", body.decode()[:800])
            # 解析 SSE 中的 result 文本
            for line in body.decode().splitlines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    print("  >> result:", json.dumps(data.get("result"), ensure_ascii=False)[:600])

        # 对照：业务 API（带业务 JWT，应续期 X-New-Access-Token；校验 exp）
        async with client.stream(
            "POST", "http://127.0.0.1:8000/api/v1/realtime/feature/query",
            headers=headers,
            json={"entity_type": "user", "entity_id": "u_1001", "feature_names": ["age"]},
        ) as r:
            b = await r.aread()
            print("\n业务 API:", r.status_code, b.decode()[:200])
            print("  X-New-Access-Token:", r.headers.get("x-new-access-token") is not None)


asyncio.run(main())
