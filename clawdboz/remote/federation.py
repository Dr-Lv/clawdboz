"""
联合群聊管理器
支持跨实例的群聊功能
"""
import asyncio
import uuid
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

from clawdboz.remote.message import RemoteMessage, MessageType


class MergeStrategy(str, Enum):
    """上下文合并策略"""
    APPEND = "append"  # 追加所有上下文
    INTERLEAVE = "interleave"  # 交错合并
    DEDUPLICATE = "deduplicate"  # 去重合并
    LATEST_ONLY = "latest_only"  # 只保留最新的


@dataclass
class FederatedGroup:
    """联合群组"""
    group_id: str
    member_instances: List[str]  # 成员实例 ID 列表
    name: str
    created_at: float
    merge_strategy: MergeStrategy = MergeStrategy.DEDUPLICATE
    context_isolation: bool = True  # 是否隔离上下文
    sequence_numbers: Dict[str, int] = field(default_factory=dict)  # 每个实例的序列号


@dataclass
class FederatedMessage:
    """联合消息"""
    message_id: str
    group_id: str
    from_instance: str
    bot_id: str
    content: str
    timestamp: float
    sequence_number: int = 0
    original_message_id: str = ""


class FederationManager:
    """联合群聊管理器"""

    def __init__(self, remote_bot_manager):
        """
        初始化联合群聊管理器

        Args:
            remote_bot_manager: RemoteBotManager 实例
        """
        self.remote_bot_mgr = remote_bot_manager

        # 联合群组 {group_id: FederatedGroup}
        self._groups: Dict[str, FederatedGroup] = {}

        # 消息历史 {group_id: List[FederatedMessage]}
        self._message_history: Dict[str, List[FederatedMessage]] = {}

        # 已处理消息（去重）{group_id: Set[str]}
        self._processed_messages: Dict[str, Set[str]] = {}

    def create_federated_group(
        self,
        member_instances: List[str],
        name: str = "",
        merge_strategy: MergeStrategy = MergeStrategy.DEDUPLICATE,
        context_isolation: bool = True
    ) -> str:
        """
        创建联合群组

        Args:
            member_instances: 成员实例 ID 列表
            name: 群组名称
            merge_strategy: 上下文合并策略
            context_isolation: 是否隔离上下文

        Returns:
            群组 ID
        """
        group_id = f"federated_{uuid.uuid4().hex[:8]}"

        # 验证实例都是好友
        for instance_id in member_instances:
            if not self._is_friend(instance_id):
                raise ValueError(f"Instance {instance_id} is not a friend")

        group = FederatedGroup(
            group_id=group_id,
            member_instances=member_instances,
            name=name or f"Federated Group {group_id}",
            created_at=asyncio.get_event_loop().time(),
            merge_strategy=merge_strategy,
            context_isolation=context_isolation
        )

        self._groups[group_id] = group
        self._message_history[group_id] = []
        self._processed_messages[group_id] = set()

        print(f"[Federation] 创建联合群组: {group_id} (成员: {len(member_instances)})")

        return group_id

    async def broadcast_to_members(
        self,
        group_id: str,
        message: str,
        chat_id: str,
        fs_api_url: str = "",
        timeout: int = 30
    ) -> Dict[str, Optional[dict]]:
        """
        向群组成员广播消息

        Args:
            group_id: 群组 ID
            message: 消息内容
            chat_id: 会话 ID
            fs_api_url: 文件访问 API URL
            timeout: 超时时间

        Returns:
            每个成员的响应 {instance_id: response}
        """
        group = self._groups.get(group_id)
        if not group:
            raise ValueError(f"Group {group_id} not found")

        responses = {}

        # 并行调用所有成员实例
        tasks = []
        for instance_id in group.member_instances:
            task = self._call_instance_bot(
                instance_id=instance_id,
                group_id=group_id,
                message=message,
                chat_id=chat_id,
                fs_api_url=fs_api_url,
                timeout=timeout
            )
            tasks.append((instance_id, task))

        # 执行所有调用
        results = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True
        )

        for i, result in enumerate(results):
            instance_id = tasks[i][0]

            if isinstance(result, Exception):
                responses[instance_id] = {
                    "success": False,
                    "error": str(result)
                }
            else:
                responses[instance_id] = result

        # 根据合并策略处理响应
        await self._merge_responses(group_id, responses, group.merge_strategy)

        return responses

    async def _call_instance_bot(
        self,
        instance_id: str,
        group_id: str,
        message: str,
        chat_id: str,
        fs_api_url: str,
        timeout: int
    ) -> dict:
        """
        调用实例的 Bot

        Args:
            instance_id: 实例 ID
            group_id: 群组 ID
            message: 消息
            chat_id: 会话 ID
            fs_api_url: 文件访问 API URL
            timeout: 超时时间

        Returns:
            Bot 响应
        """
        # 构建联合 Bot ID（使用群组 ID 作为 bot_id）
        federated_bot_id = f"{instance_id}:federated"

        # 调用远程 Bot
        result = await self.remote_bot_mgr.call_remote_bot(
            bot_id=federated_bot_id,
            method="chat",
            params={
                "message": message,
                "group_id": group_id,
                "chat_id": chat_id
            },
            chat_id=chat_id,
            fs_api_url=fs_api_url,
            timeout=timeout
        )

        return result or {"success": False, "error": "No response"}

    async def _merge_responses(
        self,
        group_id: str,
        responses: Dict[str, Optional[dict]],
        strategy: MergeStrategy
    ):
        """
        合并成员响应

        Args:
            group_id: 群组 ID
            responses: 成员响应
            strategy: 合并策略
        """
        if strategy == MergeStrategy.LATEST_ONLY:
            # 只保留最新的响应
            pass

        elif strategy == MergeStrategy.APPEND:
            # 追加所有响应
            merged_content = []
            for instance_id, response in responses.items():
                if response and response.get("success"):
                    content = response.get("result", response.get("content", ""))
                    if content:
                        merged_content.append(f"[{instance_id}]: {content}")

            if merged_content:
                print(f"[Federation] 群组 {group_id} 合并响应: {len(merged_content)} 条消息")

        elif strategy == MergeStrategy.INTERLEAVE:
            # 交错合并
            # TODO: 实现交错合并逻辑
            pass

        elif strategy == MergeStrategy.DEDUPLICATE:
            # 去重合并
            # TODO: 实现去重逻辑
            pass

    def merge_contexts(
        self,
        group_id: str,
        chat_id: str,
        max_history: int = 30
    ) -> List[dict]:
        """
        合并群组上下文

        Args:
            group_id: 群组 ID
            chat_id: 会话 ID
            max_history: 最大历史记录数

        Returns:
            合并后的上下文列表
        """
        group = self._groups.get(group_id)
        if not group:
            raise ValueError(f"Group {group_id} not found")

        if group.context_isolation:
            # 隔离上下文：每个实例独立维护上下文
            return []

        # 合并上下文
        merged_context = []

        # 按时间戳排序所有消息
        all_messages = []
        for msg in self._message_history.get(group_id, []):
            all_messages.append(msg)

        all_messages.sort(key=lambda m: m.timestamp)

        # 限制数量
        all_messages = all_messages[-max_history:]

        # 转换为上下文格式
        for msg in all_messages:
            merged_context.append({
                "role": "assistant",
                "content": msg.content,
                "bot_id": f"{msg.from_instance}:{msg.bot_id}",
                "instance_id": msg.from_instance,
                "timestamp": msg.timestamp
            })

        return merged_context

    def add_message_to_history(
        self,
        group_id: str,
        message: FederatedMessage
    ):
        """
        添加消息到历史记录

        Args:
            group_id: 群组 ID
            message: 联合消息
        """
        if group_id not in self._message_history:
            self._message_history[group_id] = []

        self._message_history[group_id].append(message)

        # 更新序列号
        if message.from_instance not in group.member_instances:
            return

        # 获取群组信息
        group = self._groups.get(group_id)
        if group:
            instance_seq = group.sequence_numbers.get(message.from_instance, 0)
            message.sequence_number = instance_seq + 1
            group.sequence_numbers[message.from_instance] = message.sequence_number

    def mark_message_processed(self, group_id: str, message_id: str):
        """
        标记消息已处理

        Args:
            group_id: 群组 ID
            message_id: 消息 ID
        """
        if group_id not in self._processed_messages:
            self._processed_messages[group_id] = set()

        self._processed_messages[group_id].add(message_id)

    def is_message_processed(self, group_id: str, message_id: str) -> bool:
        """
        检查消息是否已处理

        Args:
            group_id: 群组 ID
            message_id: 消息 ID

        Returns:
            是否已处理
        """
        return message_id in self._processed_messages.get(group_id, set())

    def get_group(self, group_id: str) -> Optional[FederatedGroup]:
        """
        获取群组信息

        Args:
            group_id: 群组 ID

        Returns:
            群组信息或 None
        """
        return self._groups.get(group_id)

    def get_all_groups(self) -> List[FederatedGroup]:
        """
        获取所有群组

        Returns:
            群组列表
        """
        return list(self._groups.values())

    def _is_friend(self, instance_id: str) -> bool:
        """
        检查是否是好友

        Args:
            instance_id: 实例 ID

        Returns:
            是否是好友
        """
        if not self.remote_bot_mgr:
            return False

        return self.remote_bot_mgr.friend_manager.is_friend(instance_id)
