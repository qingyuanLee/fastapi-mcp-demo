"""复现：FastAPI 未显式 operation_id 时生成的长工具名"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_internal_user
from app.models.common import ok

router = APIRouter(tags=["mcp_public"])


class NamingQuery(BaseModel):
    demo_id: str = Field(..., description="演示 ID")


@router.post(
    "/naming/demo",
    summary="命名演示接口（故意不写 operation_id）",
)
async def query_naming_demo(
    req: NamingQuery, user_id: str = Depends(get_internal_user)
):
    return ok({"demo_id": req.demo_id, "user_id": user_id})
