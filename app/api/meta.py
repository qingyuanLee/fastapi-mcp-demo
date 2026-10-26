"""元数据类工具（验证项目：1 个）"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_internal_user
from app.models.common import ok

router = APIRouter(tags=["mcp_public"])


class EntityMetaQuery(BaseModel):
    entity_type: str = Field(..., description="实体类型")
    entity_id: str = Field(..., description="实体 ID")


@router.post(
    "/meta/entity/meta",
    operation_id="query_entity_meta",
    summary="查询实体元数据",
)
async def query_entity_meta(
    req: EntityMetaQuery, user_id: str = Depends(get_internal_user)
):
    return ok(
        {
            "entity_type": req.entity_type,
            "entity_id": req.entity_id,
            "user_id": user_id,
        }
    )
