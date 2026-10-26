"""端到端冒烟测试：ASGITransport 直连主应用，捕获真实 traceback"""

import asyncio
import datetime
import traceback

import httpx2
import jwt

from app.config import settings
from app.main import app, mcp_app
from app.mcp_runtime import ensure_mcp_started, stop_mcp

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "smoke", "version": "1.0"},
    },
}


async def main():
    await ensure_mcp_started(mcp_app)
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/health")
        print("1. health:", r.status_code, r.text)

        r = await c.post("/mcp/", json=INIT)
        print("2. init no token:", r.status_code, r.text[:200])

        token = jwt.encode(
            {
                "sub": "u_demo_001",
                "exp": datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(hours=1),
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        try:
            r = await c.post("/mcp/", headers={"Authorization": f"Bearer {token}"}, json=INIT)
            print("3. init with token:", r.status_code, r.text[:400])
        except Exception:
            print("3. init with token EXCEPTION:")
            traceback.print_exc()

        try:
            r = await c.post(
                "/mcp/",
                headers={"Authorization": f"Bearer {token}"},
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            print("4. tools/list:", r.status_code, r.text[:600])
        except Exception:
            print("4. tools/list EXCEPTION:")
            traceback.print_exc()

    await stop_mcp()


asyncio.run(main())
