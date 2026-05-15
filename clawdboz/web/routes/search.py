"""
本地Bot搜索API
只搜索本地实例的bot
"""
from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional, Dict

router = APIRouter(prefix="/api/search", tags=["search"])


def setup_search_routes(web_server):
    """设置搜索路由，传入WebServer实例以访问本地bot列表"""
    # 将WebServer实例保存到router的state中，供后续使用
    router.state = {"web_server": web_server}

    @router.get("/bots")
    async def search_bots(
        query: str = Query("", description="搜索关键词"),
        token: str = Query(..., description="认证token")
    ):
        """
        本地Bot搜索接口（只搜索本地）

        Args:
            query: 搜索关键词
            token: 认证token

        Returns:
            本地bot的搜索结果
        """
        results = {
            "success": True,
            "query": query,
            "bots": []
        }

        if not query:
            return results

        try:
            # 从router state获取WebServer实例
            ws = router.state.get("web_server")
            if not ws:
                raise Exception("WebServer实例未初始化")

            # 获取本地bot列表
            local_bots = []
            for bot_id, bot_instance in ws.bots.items():
                # 构造bot对象（与前端格式一致）
                bot_info = {
                    "id": bot_id,
                    "name": getattr(bot_instance, 'name', bot_id),
                    "description": getattr(bot_instance, 'bio', '')
                }
                local_bots.append(bot_info)

            query_lower = query.lower()

            for bot in local_bots:
                # 搜索bot的id、name和description字段
                bot_id = bot.get("id", "").lower()
                name = bot.get("name", "").lower()
                description = bot.get("description", "").lower()

                # 搜索匹配
                if (query_lower in bot_id or
                    query_lower in name or
                    query_lower in description):

                    results["bots"].append({
                        "id": bot.get("id"),
                        "name": bot.get("name") or bot.get("id"),
                        "type": "local",
                        "description": bot.get("description", "")
                    })

            print(f"[Search] 本地搜索 '{query}': 找到 {len(results['bots'])} 个bot")

        except Exception as e:
            print(f"[Search] 搜索失败: {e}")
            raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")

        results["total"] = len(results["bots"])

        return results

    return router
