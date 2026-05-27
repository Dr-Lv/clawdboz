"""
Bot 发布管理模块
负责发布和取消发布本地 Bot 到远程注册服务器
"""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from pathlib import Path
import time
import asyncio


@dataclass
class PublishedBot:
    """发布的远程 Bot"""
    bot_id: str  # 本地 Bot ID
    instance_id: str  # 所属实例 ID
    display_name: str  # 显示名称
    description: str  # 描述
    capabilities: List[str]  # 能力列表
    is_sandboxed: bool  # 是否沙箱运行
    requires_fs_access: bool = False  # 是否需要文件访问
    avatar_color: str = ""  # 头像颜色
    avatar_icon: str = ""  # 头像图标
    avatar_image: str = ""  # 头像图片 URL
    created_at: float = field(default_factory=time.time)
    enabled: bool = True  # 是否启用

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PublishedBot":
        """从字典创建"""
        return cls(**data)


class BotPublisher:
    """Bot 发布管理器"""

    def __init__(
        self,
        instance_id: str,
        registry_client,
        storage_path: Optional[Path] = None,
        sandbox_mgr=None
    ):
        """
        初始化 Bot 发布管理器

        Args:
            instance_id: 当前实例 ID
            registry_client: 注册服务器客户端
            storage_path: 发布信息存储路径
            sandbox_mgr: Docker 沙箱管理器
        """
        self.instance_id = instance_id
        self.registry_client = registry_client
        self.storage_path = storage_path or Path("WORKPLACE") / ".remote" / "published_bots.json"
        self._sandbox_mgr = sandbox_mgr

        # 确保 storage 目录存在
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # 已发布的 Bot 列表
        self._published_bots: Dict[str, PublishedBot] = {}

        # 加载已发布的 Bot
        self._load_published_bots()

    def _load_published_bots(self):
        """从文件加载已发布的 Bot"""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for bot_id, bot_data in data.items():
                    self._published_bots[bot_id] = PublishedBot.from_dict(bot_data)
        except Exception as e:
            print(f"[BotPublisher] 加载发布信息失败: {e}")

    async def sync_sandbox_registrations(self):
        """同步所有已发布沙箱 bot 到沙箱容器（用于服务器重启后恢复）"""
        if not self._sandbox_mgr or not self._sandbox_mgr.is_available():
            return

        sandbox_bots = [
            bot for bot in self._published_bots.values()
            if bot.enabled and bot.is_sandboxed
        ]

        if not sandbox_bots:
            return

        print(f"[BotPublisher] 同步 {len(sandbox_bots)} 个沙箱 bot 到容器...")
        for bot in sandbox_bots:
            try:
                await self._register_to_sandbox(bot)
            except Exception as e:
                print(f"[BotPublisher] 同步沙箱注册失败 ({bot.bot_id}): {e}")

    def _save_published_bots(self):
        """保存已发布的 Bot 到文件"""
        try:
            data = {
                bot_id: bot.to_dict()
                for bot_id, bot in self._published_bots.items()
            }
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[BotPublisher] 保存发布信息失败: {e}")

    def publish_bot(
        self,
        bot_id: str,
        display_name: str,
        description: str = "",
        capabilities: Optional[List[str]] = None,
        is_sandboxed: bool = True,
        requires_fs_access: bool = False
    ) -> PublishedBot:
        """
        发布本地 Bot 到远程

        Args:
            bot_id: 本地 Bot ID
            display_name: 显示名称
            description: 描述
            capabilities: 能力列表
            is_sandboxed: 是否沙箱运行
            requires_fs_access: 是否需要文件访问

        Returns:
            PublishedBot 对象

        Raises:
            ValueError: Bot 已存在或参数无效
        """
        if bot_id in self._published_bots:
            raise ValueError(f"Bot '{bot_id}' 已经发布")

        if not display_name:
            raise ValueError("display_name 不能为空")

        # 从 .bot.md 读取头像信息
        avatar = self._read_bot_avatar(bot_id)

        # 创建 PublishedBot
        published_bot = PublishedBot(
            bot_id=bot_id,
            instance_id=self.instance_id,
            display_name=display_name,
            description=description,
            capabilities=capabilities or [],
            is_sandboxed=is_sandboxed,
            requires_fs_access=requires_fs_access,
            avatar_color=avatar["avatar_color"],
            avatar_icon=avatar["avatar_icon"],
            avatar_image=avatar["avatar_image"]
        )

        # 添加到发布列表
        self._published_bots[bot_id] = published_bot

        # 保存到文件
        self._save_published_bots()

        # 通知注册服务器
        self._notify_registry()

        # 如果启用沙箱，注册到沙箱容器
        if is_sandboxed and self._sandbox_mgr and self._sandbox_mgr.is_available():
            try:
                asyncio.create_task(self._register_to_sandbox(published_bot))
            except Exception as e:
                print(f"[BotPublisher] 沙箱注册失败: {e}")

        print(f"[BotPublisher] Bot '{bot_id}' 发布成功")
        return published_bot

    def _read_bot_system_prompt(self, bot_id: str) -> str:
        """从 .bot.md 读取 Bot system prompt (Bio)"""
        base_workplace = self.storage_path.parent.parent
        bot_md_path = base_workplace / f"workplace_{bot_id}" / ".bot.md"
        if not bot_md_path.exists():
            return ""
        try:
            with open(bot_md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
                name = ""
                bio = ""
                # Extract Name and Bio
                for line in md_content.split('\n'):
                    line = line.strip()
                    if line.startswith('Name:'):
                        name = line.replace('Name:', '').strip()
                    elif line.startswith('Bio:'):
                        bio = line.replace('Bio:', '').strip()
                # Build a stronger system prompt
                if name and bio:
                    # If bio is too short/generic, enhance it
                    if len(bio) < 20 or 'skill' in bio.lower():
                        return f"你是{name}。{bio}。请始终以{name}的身份回答用户的问题。"
                    return f"你是{name}。{bio}"
                elif bio:
                    return bio
                elif name:
                    return f"你是{name}。请始终以{name}的身份回答用户的问题。"
                # Fallback: use first heading
                for line in md_content.split('\n'):
                    line = line.strip()
                    if line.startswith('# '):
                        return f"你是{line.replace('# ', '').strip()}。请以此身份回答用户的问题。"
        except Exception:
            pass
        return ""

    async def _register_to_sandbox(self, published_bot: PublishedBot):
        """注册 bot 到沙箱容器"""
        try:
            system_prompt = self._read_bot_system_prompt(published_bot.bot_id)
            bot_config = {
                "display_name": published_bot.display_name,
                "description": published_bot.description,
                "capabilities": published_bot.capabilities,
                "requires_fs_access": published_bot.requires_fs_access,
                "system_prompt": system_prompt,
                "bio": system_prompt
            }
            from clawdboz.config import CONFIG
            await self._sandbox_mgr.register_bot(
                bot_id=published_bot.bot_id,
                config=bot_config,
                acp_config=CONFIG.get("acp", {})
            )
        except Exception as e:
            print(f"[BotPublisher] 沙箱注册异常: {e}")

    def unpublish_bot(self, bot_id: str) -> bool:
        """
        取消发布 Bot

        Args:
            bot_id: Bot ID

        Returns:
            是否成功
        """
        if bot_id not in self._published_bots:
            print(f"[BotPublisher] Bot '{bot_id}' 未发布")
            return False

        # 从发布列表移除
        del self._published_bots[bot_id]

        # 保存到文件
        self._save_published_bots()

        # 通知注册服务器
        self._notify_registry()

        print(f"[BotPublisher] Bot '{bot_id}' 已取消发布")
        return True

    def get_published_bots(self, include_disabled: bool = False) -> List[PublishedBot]:
        """
        获取已发布的 Bot 列表

        Args:
            include_disabled: 是否包含已禁用的 Bot

        Returns:
            PublishedBot 列表
        """
        bots = list(self._published_bots.values())

        if not include_disabled:
            bots = [bot for bot in bots if bot.enabled]

        return bots

    def get_published_bot(self, bot_id: str) -> Optional[PublishedBot]:
        """
        获取指定的已发布 Bot

        Args:
            bot_id: Bot ID

        Returns:
            PublishedBot 对象或 None
        """
        return self._published_bots.get(bot_id)

    def enable_bot(self, bot_id: str) -> bool:
        """启用已发布的 Bot"""
        bot = self._published_bots.get(bot_id)
        if bot:
            bot.enabled = True
            self._save_published_bots()
            self._notify_registry()
            return True
        return False

    def disable_bot(self, bot_id: str) -> bool:
        """禁用已发布的 Bot"""
        bot = self._published_bots.get(bot_id)
        if bot:
            bot.enabled = False
            self._save_published_bots()
            self._notify_registry()
            return True
        return False

    def _read_bot_avatar(self, bot_id: str) -> dict:
        """从 .bot.md 读取 Bot 头像信息"""
        base_workplace = self.storage_path.parent.parent
        bot_md_path = base_workplace / f"workplace_{bot_id}" / ".bot.md"
        avatar = {"avatar_color": "", "avatar_icon": "", "avatar_image": ""}
        if not bot_md_path.exists():
            return avatar
        try:
            with open(bot_md_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('Avatar Color:'):
                        avatar["avatar_color"] = line.replace('Avatar Color:', '').strip()
                    elif line.startswith('Avatar Icon:'):
                        avatar["avatar_icon"] = line.replace('Avatar Icon:', '').strip()
                    elif line.startswith('Avatar Image:'):
                        avatar["avatar_image"] = line.replace('Avatar Image:', '').strip()
        except Exception:
            pass
        return avatar

    def _notify_registry(self):
        """通知注册服务器更新 Bot 列表（同步版本）"""
        try:
            # 获取所有启用的 Bot ID 和完整信息
            enabled_bots = [
                bot for bot in self._published_bots.values()
                if bot.enabled
            ]

            enabled_bot_ids = [bot.bot_id for bot in enabled_bots]

            # 构建完整的 bot 信息列表（包含最新头像信息）
            published_bots_info = []
            for bot in enabled_bots:
                # 从 .bot.md 读取最新头像信息并更新 PublishedBot 对象
                avatar = self._read_bot_avatar(bot.bot_id)
                bot.avatar_color = avatar["avatar_color"]
                bot.avatar_icon = avatar["avatar_icon"]
                bot.avatar_image = avatar["avatar_image"]

                bot_info = {
                    "bot_id": bot.bot_id,
                    "display_name": bot.display_name,
                    "description": bot.description,
                    "capabilities": bot.capabilities,
                    "is_sandboxed": bot.is_sandboxed,
                    "requires_fs_access": bot.requires_fs_access
                }
                bot_info.update(avatar)
                published_bots_info.append(bot_info)

            # 保存更新后的头像信息
            self._save_published_bots()

            # 更新实例信息中的 published_bots 字段
            if hasattr(self.registry_client, 'instance_info'):
                self.registry_client.instance_info['published_bots'] = enabled_bot_ids
                self.registry_client.instance_info['published_bots_info'] = published_bots_info

            # 发送心跳更新
            if hasattr(self.registry_client, 'send_heartbeat'):
                self.registry_client.send_heartbeat()

            print(f"[BotPublisher] 已通知注册服务器: {len(enabled_bot_ids)} 个 Bot")

        except Exception as e:
            print(f"[BotPublisher] 通知注册服务器失败: {e}")

    def is_bot_published(self, bot_id: str) -> bool:
        """检查 Bot 是否已发布"""
        return bot_id in self._published_bots

    def get_published_bot_ids(self) -> List[str]:
        """获取已发布的 Bot ID 列表"""
        return list(self._published_bots.keys())
