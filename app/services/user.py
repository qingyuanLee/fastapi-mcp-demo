"""用户查询（验证项目用内存数据，现网替换为存量逻辑）"""

_USERS = {
    "u_demo_001": {"id": "u_demo_001", "is_active": True, "name": "demo"},
    "u_demo_002": {"id": "u_demo_002", "is_active": True, "name": "demo2"},
}


async def get_user_by_id(user_id: str):
    return _USERS.get(user_id)
