#!/usr/bin/env python3
"""
朋友圈数据管理模块

处理朋友圈数据的加载、保存和管理。
"""

import json
import os
import re
from typing import Dict, List, Optional, Any


class MomentsDataManager:
    """
    朋友圈数据管理器

    管理朋友圈数据的持久化存储，包括动态、点赞和评论。
    """

    def __init__(self, base_workplace: str):
        """
        初始化数据管理器

        Args:
            base_workplace: 基础 workplace 目录路径
        """
        self.base_workplace = base_workplace

    def _get_moments_file_path(self) -> str:
        """获取朋友圈数据文件路径"""
        moments_dir = os.path.join(self.base_workplace, 'moments')
        os.makedirs(moments_dir, exist_ok=True)
        return os.path.join(moments_dir, 'moments.json')

    def load_moments(self) -> List[Dict[str, Any]]:
        """加载朋友圈数据"""
        file_path = self._get_moments_file_path()
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Moments] 加载失败: {e}")
        return []

    def save_moments(self, moments: List[Dict[str, Any]]):
        """保存朋友圈数据"""
        file_path = self._get_moments_file_path()
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(moments, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Moments] 保存失败: {e}")

    def get_sender_info(self, sender_id: str, sender_type: str = 'user',
                        bots: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        获取发送者信息

        Args:
            sender_id: 发送者 ID
            sender_type: 发送者类型 ('user' 或 'bot')
            bots: Bot 对象字典，用于获取 Bot 信息

        Returns:
            发送者信息字典
        """
        if sender_type == 'user':
            # 从 .user.md 获取用户信息
            user_file = os.path.join(self.base_workplace, '.user.md')
            name = "用户"
            avatar_color = "from-blue-400 to-blue-600"
            avatar_icon = "fa-user"

            if os.path.exists(user_file):
                try:
                    with open(user_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('Name:'):
                                name = line.replace('Name:', '').strip()
                            elif line.startswith('Avatar Color:'):
                                color = line.replace('Avatar Color:', '').strip()
                                if color:
                                    avatar_color = color
                            elif line.startswith('Avatar Icon:'):
                                icon = line.replace('Avatar Icon:', '').strip()
                                if icon:
                                    avatar_icon = icon
                except Exception as e:
                    print(f"[Sender Info] 读取用户文件失败: {e}")

            return {
                'id': 'user',
                'name': name or '用户',
                'type': 'user',
                'avatar_color': avatar_color,
                'avatar_icon': avatar_icon
            }
        else:
            # 获取 Bot 信息
            name = sender_id
            avatar_color = "from-purple-400 to-purple-600"
            avatar_icon = "fa-robot"

            # 尝试从 bot 对象获取名称
            if bots and sender_id in bots:
                bot = bots[sender_id]
                name = getattr(bot, 'name', sender_id)

            # 从 workplace_{sender_id}/.bot.md 读取
            bot_file = os.path.join(self.base_workplace, f"workplace_{sender_id}", '.bot.md')

            if os.path.exists(bot_file):
                try:
                    with open(bot_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        lines = content.split('\n')

                        # 1. 尝试从第一行读取名称（# Bot Name）
                        if lines and lines[0].startswith('# '):
                            first_line_name = lines[0][2:].strip()
                            # 如果第一行不是通用的"Bot 配置"，则使用它
                            if first_line_name and first_line_name != 'Bot 配置':
                                name = first_line_name

                        # 2. 继续读取其他字段，并尝试从内容中提取 Bot 名称
                        for line in lines[1:]:
                            if line.startswith('Name:'):
                                name_from_file = line.replace('Name:', '').strip()
                                if name_from_file:
                                    name = name_from_file
                            elif line.startswith('Avatar Color:'):
                                color = line.replace('Avatar Color:', '').strip()
                                if color:
                                    avatar_color = color
                            elif line.startswith('Avatar Icon:'):
                                icon = line.replace('Avatar Icon:', '').strip()
                                if icon:
                                    avatar_icon = icon

                        # 3. 如果还没有找到名称，尝试从内容中提取 "你是XXX" 或 "名字叫 XXX"
                        if name == sender_id:
                            # 匹配 "你是XXX，" 或 "名字叫 XXX" 或 "名称: XXX"
                            patterns = [
                                r'你是\*\*(.+?)\*\*[，,，]',
                                r'你是(.+?)[，,，]',
                                r'名字叫\s*(.+?)[，,，\n]',
                                r'名称[：:]\s*(.+)'
                            ]
                            for pattern in patterns:
                                match = re.search(pattern, content)
                                if match:
                                    name = match.group(1).strip()
                                    break
                except Exception as e:
                    print(f"[Sender Info] 读取 bot 文件失败: {e}")

            return {
                'id': sender_id,
                'name': name,
                'type': 'bot',
                'avatar_color': avatar_color,
                'avatar_icon': avatar_icon
            }
