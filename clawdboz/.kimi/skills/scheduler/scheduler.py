#!/usr/bin/env python3
"""
定时任务 Skill - 简单的任务文件管理工具

这个模块只提供对 scheduler_tasks.json 文件的操作工具，
不负责实际的任务调度。任务调度由 Bot 的心跳线程自动处理。

任务文件格式 (WORKPLACE/scheduler_tasks.json):
{
  "task_id_counter": 1,
  "tasks": {
    "1": {
      "id": 1,
      "chat_id": "oc_xxxxx",
      "description": "任务描述",
      "execute_time": 1234567890.0,  // 时间戳，可选，为空则立即执行
      "created_at": 1234567890.0,
      "status": "pending"  // pending/executing/completed/failed
    }
  }
}

使用方式：
1. 直接编辑 WORKPLACE/scheduler_tasks.json 添加/修改任务
2. Bot 心跳线程会自动检测并执行到期的任务
3. 任务执行完成后会自动更新状态为 completed 或 failed
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def get_tasks_file_path(data_dir: str = None) -> str:
    """获取任务文件路径"""
    if data_dir is None:
        from clawdboz.config import get_absolute_path
        data_dir = get_absolute_path('WORKPLACE')
    return os.path.join(data_dir, 'scheduler_tasks.json')


def load_tasks(data_dir: str = None) -> dict:
    """
    加载任务数据
    
    Returns:
        {"task_id_counter": int, "tasks": {task_id: task_data}}
    """
    tasks_file = get_tasks_file_path(data_dir)
    
    if not os.path.exists(tasks_file):
        return {'task_id_counter': 0, 'tasks': {}}
    
    try:
        with open(tasks_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[SCHEDULER] 加载任务失败: {e}")
        return {'task_id_counter': 0, 'tasks': {}}


def save_tasks(data: dict, data_dir: str = None) -> bool:
    """保存任务数据"""
    tasks_file = get_tasks_file_path(data_dir)
    
    try:
        os.makedirs(os.path.dirname(tasks_file), exist_ok=True)
        with open(tasks_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[SCHEDULER] 保存任务失败: {e}")
        return False


def create_task(chat_id: str, description: str, execute_time: float = None, data_dir: str = None) -> Optional[int]:
    """
    创建新任务
    
    Args:
        chat_id: 聊天 ID
        description: 任务描述
        execute_time: 执行时间戳，None 表示立即执行
        data_dir: 数据目录
        
    Returns:
        任务 ID，失败返回 None
    """
    data = load_tasks(data_dir)
    
    # 生成新任务 ID
    data['task_id_counter'] = data.get('task_id_counter', 0) + 1
    task_id = data['task_id_counter']
    
    # 创建任务
    data['tasks'][str(task_id)] = {
        'id': task_id,
        'chat_id': chat_id,
        'description': description,
        'execute_time': execute_time,
        'created_at': time.time(),
        'status': 'pending'
    }
    
    if save_tasks(data, data_dir):
        print(f"[SCHEDULER] 创建任务 #{task_id}: {description[:50]}")
        return task_id
    return None


def update_task(task_id: int, updates: dict, data_dir: str = None) -> bool:
    """
    更新任务
    
    Args:
        task_id: 任务 ID
        updates: 要更新的字段字典
        data_dir: 数据目录
        
    Returns:
        是否成功
    """
    data = load_tasks(data_dir)
    task_id_str = str(task_id)
    
    if task_id_str not in data['tasks']:
        return False
    
    # 更新字段
    data['tasks'][task_id_str].update(updates)
    data['tasks'][task_id_str]['updated_at'] = time.time()
    
    return save_tasks(data, data_dir)


def delete_task(task_id: int, data_dir: str = None) -> bool:
    """
    删除任务
    
    Args:
        task_id: 任务 ID
        data_dir: 数据目录
        
    Returns:
        是否成功
    """
    data = load_tasks(data_dir)
    task_id_str = str(task_id)
    
    if task_id_str not in data['tasks']:
        return False
    
    del data['tasks'][task_id_str]
    return save_tasks(data, data_dir)


def list_tasks(chat_id: str = None, status: str = None, data_dir: str = None) -> List[dict]:
    """
    列出任务
    
    Args:
        chat_id: 过滤特定聊天，None 表示所有
        status: 过滤特定状态，None 表示所有
        data_dir: 数据目录
        
    Returns:
        任务列表
    """
    data = load_tasks(data_dir)
    tasks = []
    
    for task in data['tasks'].values():
        if chat_id is not None and task.get('chat_id') != chat_id:
            continue
        if status is not None and task.get('status') != status:
            continue
        tasks.append(task)
    
    return tasks


def get_task(task_id: int, data_dir: str = None) -> Optional[dict]:
    """
    获取单个任务
    
    Args:
        task_id: 任务 ID
        data_dir: 数据目录
        
    Returns:
        任务数据，不存在返回 None
    """
    data = load_tasks(data_dir)
    return data['tasks'].get(str(task_id))


def parse_time(time_str: str) -> Optional[float]:
    """
    解析时间字符串为时间戳
    
    支持格式：
    - "10分钟后" / "10 mins"
    - "1小时后" / "1 hour"
    - "明天上午9点"
    - "今天下午3点"
    - "2024-01-15 09:00"
    
    Args:
        time_str: 时间字符串
        
    Returns:
        时间戳，解析失败返回 None
    """
    if time_str is None or time_str == '':
        return None
    
    now = datetime.now()
    time_str = time_str.strip().lower()
    
    try:
        # 尝试解析绝对时间 (YYYY-MM-DD HH:MM)
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            return dt.timestamp()
        except ValueError:
            pass
        
        # 尝试解析只有时间 (HH:MM)，默认今天，已过则明天
        try:
            dt = datetime.strptime(time_str, "%H:%M")
            dt = now.replace(hour=dt.hour, minute=dt.minute, second=0, microsecond=0)
            if dt < now:
                dt += timedelta(days=1)
            return dt.timestamp()
        except ValueError:
            pass
        
        # 相对时间：X分钟后
        match = re.match(r'(\d+)\s*分钟后?', time_str)
        if match:
            minutes = int(match.group(1))
            return (now + timedelta(minutes=minutes)).timestamp()
        
        # 相对时间：X小时后
        match = re.match(r'(\d+)\s*小时后?', time_str)
        if match:
            hours = int(match.group(1))
            return (now + timedelta(hours=hours)).timestamp()
        
        # 相对时间：X天后
        match = re.match(r'(\d+)\s*天后?', time_str)
        if match:
            days = int(match.group(1))
            return (now + timedelta(days=days)).timestamp()
        
        # 明天上午/下午X点
        match = re.match(r'明天\s*(上午|下午)?\s*(\d+)\s*点?', time_str)
        if match:
            am_pm = match.group(1)
            hour = int(match.group(2))
            
            if am_pm == '下午' and hour < 12:
                hour += 12
            
            dt = now + timedelta(days=1)
            dt = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
            return dt.timestamp()
        
        # 今天/下午X点
        match = re.match(r'(今天)?\s*(上午|下午)?\s*(\d+)\s*点?', time_str)
        if match:
            am_pm = match.group(2)
            hour = int(match.group(3))
            
            if am_pm == '下午' and hour < 12:
                hour += 12
            
            dt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if dt < now:
                dt += timedelta(days=1)
            return dt.timestamp()
        
        return None
        
    except Exception as e:
        print(f"[SCHEDULER] 解析时间失败: {e}")
        return None


def format_task_list(tasks: List[dict]) -> str:
    """格式化任务列表为可读文本"""
    if not tasks:
        return "暂无定时任务"
    
    lines = ["📋 **定时任务列表**\n"]
    
    for task in sorted(tasks, key=lambda x: x.get('execute_time') or 0):
        task_id = task['id']
        description = task['description']
        execute_time = task.get('execute_time')
        status = task.get('status', 'pending')
        
        # 格式化时间
        if execute_time:
            dt = datetime.fromtimestamp(execute_time)
            time_str = dt.strftime("%Y-%m-%d %H:%M")
            
            # 计算剩余时间
            remaining = execute_time - time.time()
            if remaining < 60:
                remaining_str = "即将执行"
            elif remaining < 3600:
                remaining_str = f"{int(remaining/60)}分钟后"
            elif remaining < 86400:
                remaining_str = f"{int(remaining/3600)}小时后"
            else:
                remaining_str = f"{int(remaining/86400)}天后"
            time_display = f"{time_str} ({remaining_str})"
        else:
            time_display = "立即执行"
        
        # 状态图标
        status_icon = {
            'pending': '⏳',
            'executing': '🔄',
            'completed': '✅',
            'failed': '❌'
        }.get(status, '⏳')
        
        lines.append(f"{status_icon} **#{task_id}** - {time_display}")
        lines.append(f"   {description[:50]}{'...' if len(description) > 50 else ''}\n")
    
    return "\n".join(lines)


def format_time(timestamp: float) -> str:
    """将时间戳格式化为可读字符串"""
    if timestamp is None:
        return "未设置"
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M")
