"""MCP 惰性生命周期管理（不占用主应用 lifespan）

背景：主 FastAPI 的 lifespan 已被原系统业务占用且逻辑复杂，本模块不注册、不组合 lifespan，
改为"首个 /mcp 请求幂等进入 mcp_app.lifespan 并保持到进程结束"。
依据（fastmcp 4.1.0 源码）：mcp_app.lifespan 创建 FastMCPStreamableHTTPSessionManager
并 async with session_manager.run()；不运行则 /mcp 请求报错 "lifespan is not run"。
已知取舍：进程退出时不保证调用 __aexit__（Starlette 1.x 中 lifespan 与 on_event 互斥、
覆盖 uvicorn 信号 handler 会破坏 graceful shutdown，故不注册）；单 worker 退出即整体释放。
"""

import asyncio
from contextlib import _AsyncGeneratorContextManager
from typing import Optional

_lock: Optional[asyncio.Lock] = None
_ctx: Optional[_AsyncGeneratorContextManager] = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def ensure_mcp_started(mcp_app) -> None:
    """幂等进入 mcp_app.lifespan；并发安全（首个请求初始化，之后保持）"""
    global _ctx
    if _ctx is not None:
        return
    async with _get_lock():
        if _ctx is not None:
            return
        ctx = mcp_app.lifespan(mcp_app)
        await ctx.__aenter__()
        _ctx = ctx


async def stop_mcp() -> None:
    """进程退出前的优雅清理（可选；单 worker 退出即整体释放，非必须）"""
    global _ctx
    if _ctx is None:
        return
    await _ctx.__aexit__(None, None, None)
    _ctx = None
