"""实时特征类工具（验证项目：1 个）"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_internal_user
from app.models.common import ok

router = APIRouter(tags=["mcp_public"])


class RealtimeFeatureQuery(BaseModel):
    entity_type: str = Field(..., description="实体类型")
    entity_id: str = Field(..., description="实体 ID")
    feature_names: list[str] = Field(..., description="特征名列表")


@router.post(
    "/realtime/feature/query",
    operation_id="query_realtime_feature",
    summary="查询用户实时特征值",
)
async def query_realtime_feature(
    req: RealtimeFeatureQuery, user_id: str = Depends(get_internal_user)
):
    return ok(
        {
            "entity_id": req.entity_id,
            "values": {f: 1.0 for f in req.feature_names},
            "user_id": user_id,
        }
    )
