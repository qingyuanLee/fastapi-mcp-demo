"""离线特征类工具（验证项目：1 个）"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_internal_user
from app.models.common import ok

router = APIRouter(tags=["mcp_public"])


class OfflineFeatureQuery(BaseModel):
    entity_type: str = Field(..., description="实体类型")
    entity_id: str = Field(..., description="实体 ID")
    feature_names: list[str] = Field(..., description="特征名列表")
    date: str = Field(default="2026-10-12", description="数据日期")


@router.post(
    "/offline/feature/query",
    operation_id="query_offline_feature",
    summary="查询离线特征值",
)
async def query_offline_feature(
    req: OfflineFeatureQuery, user_id: str = Depends(get_internal_user)
):
    return ok(
        {
            "entity_id": req.entity_id,
            "values": {f: 0.5 for f in req.feature_names},
            "date": req.date,
            "user_id": user_id,
        }
    )
