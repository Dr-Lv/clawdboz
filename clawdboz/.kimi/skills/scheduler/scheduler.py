#!/usr/bin/env python3
"""
定时任务 Skill - 纯数据管理，不执行调度

职责：
- 定义标准的数据格式和接口
- 读写 scheduler_tasks.json 文件
- 提供任务 CRUD 接口
- 不负责自然语言解析和时区转换（由调用方处理）

JSON 格式规范：
{
  "task_id_counter": 3,
  "tasks": {
    "1": {
      "id": "1",
      "chat_id": "oc_xxx",
      "execute_time": 1771526400,      // 必填，Unix时间戳（UTC）
      "time_interval": 60,              // 可选，重复周期（秒）
      "description": "任务描述",
      "status": "pending"               // pending/running/completed/failed
    }
  }
}

注意：
- 本 skill 只负责数据管理，不执行任务
- 本 skill 不负责时间字符串解析（由调用方处理）
- 所有时间戳必须是 UTC 时间戳（正数）
- 任务执行由外部心跳机制（如 bot）处理
"""

import json
import os
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional


class TaskScheduler:
    """定时任务数据管理器 - 无调度功能，无时间解析"""
    
    def __init__(self, data_dir: str = None):
        self._lock = threading.Lock()
        
        # 数据文件路径
        if data_dir is None:
            data_dir = self._find_workplace_dir()
        else:
            # 处理相对路径，避免 WORKPLACE/WORKPLACE 问题
            # 如果当前目录已经是 WORKPLACE，且传入的是 ./WORKPLACE，直接使用当前目录
            if data_dir in ('./WORKPLACE', 'WORKPLACE') and os.path.basename(os.getcwd()) == 'WORKPLACE':
                data_dir = os.getcwd()
            else:
                # 将相对路径转换为绝对路径
                data_dir = os.path.abspath(data_dir)
        
        self.data_dir = data_dir
        self.data_file = os.path.join(data_dir, 'scheduler_tasks.json')
        
        os.makedirs(data_dir, exist_ok=True)
    
    def _find_workplace_dir(self) -> str:
        """查找工作目录"""
        if 'CLAWDBOZ_WORKPLACE' in os.environ:
            return os.environ['CLAWDBOZ_WORKPLACE']
        
        current_dir = os.getcwd()
        
        # 如果当前目录名已经是 WORKPLACE，直接返回
        if os.path.basename(current_dir) == 'WORKPLACE':
            return current_dir
        
        for _ in range(10):
            workplace = os.path.join(current_dir, 'WORKPLACE')
            if os.path.isdir(workplace):
                return workplace
            
            if os.path.isdir(os.path.join(current_dir, '.kimi')):
                workplace = os.path.join(current_dir, 'WORKPLACE')
                os.makedirs(workplace, exist_ok=True)
                return workplace
            
            parent = os.path.dirname(current_dir)
            if parent == current_dir:
                break
            current_dir = parent
        
        return os.getcwd()
    
    def _save_data(self, data: dict):
        """原子写入 JSON 文件"""
        with self._lock:
            temp_file = self.data_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, self.data_file)
    
    def _load_data(self) -> dict:
        """加载 JSON 文件"""
        if not os.path.exists(self.data_file):
            return {'task_id_counter': 0, 'tasks': {}}
        
        with open(self.data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def create_task(self, chat_id: str, description: str, execute_time: float, 
                    time_interval: int = None) -> str:
        """
        创建定时任务
        
        Args:
            chat_id: 聊天 ID
            description: 任务描述
            execute_time: 执行时间戳（UTC Unix timestamp，必须为正数）
            time_interval: 重复间隔（秒），None 表示一次性任务
            
        Returns:
            task_id: 任务 ID
            
        Raises:
            ValueError: 如果 execute_time 不是正数
        """
        if execute_time <= 0:
            raise ValueError("execute_time 必须是正数 UTC 时间戳")
        
        data = self._load_data()
        data['task_id_counter'] += 1
        task_id = str(data['task_id_counter'])
        
        task = {
            'id': task_id,
            'chat_id': chat_id,
            'execute_time': float(execute_time),
            'description': description,
            'status': 'pending'
        }
        
        if time_interval is not None and time_interval > 0:
            task['time_interval'] = int(time_interval)
        
        data['tasks'][task_id] = task
        self._save_data(data)
        
        return task_id
    
    def get_task(self, task_id: str) -> Optional[dict]:
        """获取单个任务"""
        data = self._load_data()
        task = data['tasks'].get(str(task_id))
        return task.copy() if task else None
    
    def list_tasks(self, chat_id: str = None, status: str = None) -> List[dict]:
        """列出任务"""
        data = self._load_data()
        tasks = []
        
        for task in data['tasks'].values():
            if chat_id and task['chat_id'] != chat_id:
                continue
            if status and task['status'] != status:
                continue
            tasks.append(task.copy())
        
        tasks.sort(key=lambda x: x['execute_time'])
        return tasks
    
    def update_task(self, task_id: str, **kwargs) -> bool:
        """更新任务字段"""
        allowed_fields = {'description', 'execute_time', 'time_interval', 'status'}
        
        data = self._load_data()
        task_id = str(task_id)
        
        if task_id not in data['tasks']:
            return False
        
        task = data['tasks'][task_id]
        
        for key, value in kwargs.items():
            if key not in allowed_fields:
                continue
            
            if key == 'execute_time' and value <= 0:
                raise ValueError("execute_time 必须是正数")
            
            if key == 'time_interval':
                if value is None:
                    task.pop('time_interval', None)
                    continue
                elif value <= 0:
                    raise ValueError("time_interval 必须是正数或 None")
            
            task[key] = value
        
        self._save_data(data)
        return True
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        data = self._load_data()
        task_id = str(task_id)
        
        if task_id not in data['tasks']:
            return False
        
        del data['tasks'][task_id]
        self._save_data(data)
        return True
    
    def tick(self, current_time: float = None, window_start: float = None) -> List[dict]:
        """
        心跳 tick - 检查并返回需要执行的任务
        
        Args:
            current_time: 当前 UTC 时间戳（默认 time.time()）
            window_start: 检查窗口起始时间
            
        Returns:
            需要执行的任务列表
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc).timestamp()
        
        if not hasattr(self, '_last_tick_time'):
            self._last_tick_time = current_time - 60
        
        if window_start is None:
            window_start = self._last_tick_time
        
        self._last_tick_time = current_time
        
        data = self._load_data()
        tasks = data.get('tasks', {})
        
        pending_tasks = []
        for task_data in tasks.values():
            execute_time = task_data.get('execute_time')
            status = task_data.get('status', 'pending')
            
            if status != 'pending':
                continue
            
            if execute_time is None or execute_time == '':
                pending_tasks.append(task_data.copy())
            elif window_start <= execute_time <= current_time:
                pending_tasks.append(task_data.copy())
        
        return pending_tasks


# ==================== 工具函数（仅格式化，不解析） ====================

def format_task_list(tasks: List[dict], tz_offset: int = 8) -> str:
    """格式化任务列表为可读文本
    
    Args:
        tasks: 任务列表
        tz_offset: 时区偏移（小时），默认北京时间+8
    """
    if not tasks:
        return "暂无定时任务"
    
    from datetime import timezone, timedelta
    
    tz = timezone(timedelta(hours=tz_offset))
    lines = ["📋 **定时任务列表**\n"]
    
    for task in tasks:
        task_id = task['id']
        desc = task['description']
        exec_time = task['execute_time']
        is_recurring = task.get('time_interval') is not None
        
        icon = "🔄" if is_recurring else "⏰"
        dt = datetime.fromtimestamp(exec_time, tz)
        time_str = dt.strftime("%m-%d %H:%M")
        
        repeat_info = ""
        if is_recurring:
            interval = task['time_interval']
            if interval < 3600:
                repeat_info = f" (每{interval//60}分)"
            elif interval < 86400:
                repeat_info = f" (每{interval//3600}小时)"
            else:
                repeat_info = f" (每{interval//86400}天)"
        
        status_emoji = {
            'pending': '⏳',
            'running': '▶️',
            'completed': '✅',
            'failed': '❌'
        }.get(task['status'], '❓')
        
        lines.append(f"{icon} **#{task_id}** {time_str}{repeat_info} {status_emoji}")
        lines.append(f"   {desc[:30]}{'...' if len(desc) > 30 else ''}\n")
    
    return "\n".join(lines)


def format_task_detail(task: dict, tz_offset: int = 8) -> str:
    """格式化任务详情
    
    Args:
        task: 任务字典
        tz_offset: 时区偏移（小时），默认北京时间+8
    """
    from datetime import timezone, timedelta
    
    tz = timezone(timedelta(hours=tz_offset))
    task_id = task['id']
    desc = task['description']
    exec_time = task['execute_time']
    is_recurring = task.get('time_interval') is not None
    
    dt = datetime.fromtimestamp(exec_time, tz)
    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    
    lines = [f"📋 **任务 #{task_id}**\n"]
    
    if is_recurring:
        interval = task['time_interval']
        lines.append(f"🔄 **类型:** 重复任务 (每 {interval} 秒)")
    else:
        lines.append(f"⏰ **类型:** 一次性任务")
    
    status = task['status']
    status_text = {
        'pending': '⏳ 等待执行',
        'running': '▶️ 执行中',
        'completed': '✅ 已完成',
        'failed': '❌ 失败'
    }.get(status, status)
    lines.append(f"**状态:** {status_text}")
    
    lines.append(f"📅 **执行时间:** {time_str} (UTC+{tz_offset})")
    
    chat_id = task['chat_id']
    short_id = chat_id[:10] + "..." if len(chat_id) > 10 else chat_id
    lines.append(f"💬 **聊天:** {short_id}")
    
    lines.append(f"\n📝 **任务内容:**\n```\n{desc}\n```")
    
    return "\n".join(lines)


# 全局实例
_scheduler: Optional[TaskScheduler] = None


def get_scheduler(data_dir: str = None) -> TaskScheduler:
    """获取全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler(data_dir)
    elif data_dir is not None:
        # 处理相对路径，避免 WORKPLACE/WORKPLACE 问题
        if data_dir in ('./WORKPLACE', 'WORKPLACE') and os.path.basename(os.getcwd()) == 'WORKPLACE':
            data_dir = os.getcwd()
        else:
            data_dir = os.path.abspath(data_dir)
        _scheduler.data_dir = data_dir
        _scheduler.data_file = os.path.join(data_dir, 'scheduler_tasks.json')
    return _scheduler


# ==================== 便捷函数 ====================

def create_task(chat_id: str, description: str, execute_time: float, 
                time_interval: int = None, data_dir: str = None) -> str:
    """创建定时任务（execute_time 必须是 UTC 时间戳）"""
    return get_scheduler(data_dir).create_task(chat_id, description, execute_time, time_interval)


def get_task(task_id: str, data_dir: str = None) -> Optional[dict]:
    """获取单个任务"""
    return get_scheduler(data_dir).get_task(task_id)


def list_tasks(chat_id: str = None, status: str = None, data_dir: str = None) -> List[dict]:
    """列出任务"""
    return get_scheduler(data_dir).list_tasks(chat_id, status)


def update_task(task_id: str, data_dir: str = None, **kwargs) -> bool:
    """更新任务"""
    return get_scheduler(data_dir).update_task(task_id, **kwargs)


def delete_task(task_id: str, data_dir: str = None) -> bool:
    """删除任务"""
    return get_scheduler(data_dir).delete_task(task_id)


def tick(current_time: float = None, window_start: float = None, data_dir: str = None) -> List[dict]:
    """心跳 tick - 检查并返回需要执行的任务"""
    return get_scheduler(data_dir).tick(current_time, window_start)
