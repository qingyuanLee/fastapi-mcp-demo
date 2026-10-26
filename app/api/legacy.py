"""模拟老项目"其他业务接口"：不带 mcp_public tag 的存量路由（复现用）"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_internal_user
from app.models.common import ok

router = APIRouter(tags=["legacy_business"])


class LegacyQuery(BaseModel):
    biz_id: str = Field(..., description="业务 ID")


@router.post(
    "/legacy/biz/query",
    operation_id="query_legacy_biz",
    summary="存量业务查询接口（不声明 mcp_public）",
)
async def query_legacy_biz(
    req: LegacyQuery, user_id: str = Depends(get_internal_user)
):
    return ok(
        {
            "biz_id": req.biz_id,
            "user_id": user_id,
        }
    )
