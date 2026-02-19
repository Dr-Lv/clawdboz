#!/usr/bin/env python3
"""
定时任务 Skill - 在指定时间执行任务并发送结果

功能：
- 创建定时任务
- 列出所有定时任务
- 取消定时任务
- 在指定时间自动执行并发送结果给用户

使用方式：
- "设置一个定时任务，明天上午9点提醒我开会"
- "列出所有定时任务"
- "取消定时任务 #1"
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable


class TaskScheduler:
    """定时任务管理器"""
    
    def __init__(self, bot_ref=None, data_dir: str = None):
        self.bot = bot_ref
        self.tasks: Dict[int, dict] = {}
        self.task_id_counter = 0
        self._lock = threading.Lock()
        self._timers: Dict[int, threading.Timer] = {}
        
        # 数据文件路径
        if data_dir is None:
            from clawdboz.config import get_absolute_path
            data_dir = get_absolute_path('WORKPLACE')
        self.data_dir = data_dir
        self.data_file = os.path.join(data_dir, 'scheduler_tasks.json')
        
        # 确保目录存在
        os.makedirs(data_dir, exist_ok=True)
        
        # 加载已保存的任务
        self._load_tasks()
    
    def _log(self, message: str):
        """记录日志"""
        if self.bot:
            self.bot._log(f"[SCHEDULER] {message}")
        else:
            print(f"[SCHEDULER] {message}")
    
    def _save_tasks(self):
        """保存任务到文件"""
        try:
            with self._lock:
                # 只保存可序列化的数据
                save_data = {
                    'task_id_counter': self.task_id_counter,
                    'tasks': {}
                }
                for task_id, task in self.tasks.items():
                    save_data['tasks'][str(task_id)] = {
                        'id': task['id'],
                        'chat_id': task['chat_id'],
                        'description': task['description'],
                        'execute_time': task['execute_time'],
                        'created_at': task['created_at'],
                        'status': task['status']
                    }
                
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"保存任务失败: {e}")
    
    def _load_tasks(self):
        """从文件加载任务"""
        if not os.path.exists(self.data_file):
            return
        
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.task_id_counter = data.get('task_id_counter', 0)
            
            for task_id_str, task_data in data.get('tasks', {}).items():
                task_id = int(task_id_str)
                
                # 检查任务是否过期
                execute_time = task_data['execute_time']
                if execute_time < time.time():
                    # 任务已过期，跳过
                    self._log(f"任务 #{task_id} 已过期，跳过")
                    continue
                
                # 恢复任务
                with self._lock:
                    self.tasks[task_id] = {
                        'id': task_id,
                        'chat_id': task_data['chat_id'],
                        'description': task_data['description'],
                        'execute_time': execute_time,
                        'created_at': task_data.get('created_at', time.time()),
                        'status': 'pending'
                    }
                    
                    # 重新启动定时器
                    self._schedule_task(task_id)
                    
            self._log(f"已加载 {len(self.tasks)} 个待执行任务")
                    
        except Exception as e:
            self._log(f"加载任务失败: {e}")
    
    def _schedule_task(self, task_id: int):
        """为任务设置定时器"""
        with self._lock:
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            execute_time = task['execute_time']
            delay = execute_time - time.time()
            
            if delay <= 0:
                # 任务时间已过，立即执行
                delay = 0.1
            
            # 创建定时器
            timer = threading.Timer(delay, self._execute_task, args=[task_id])
            timer.daemon = True
            timer.start()
            
            self._timers[task_id] = timer
            self._log(f"任务 #{task_id} 已调度，将在 {delay:.1f} 秒后执行")
    
    def _execute_task(self, task_id: int):
        """执行定时任务"""
        with self._lock:
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            task['status'] = 'executing'
        
        try:
            self._log(f"开始执行任务 #{task_id}: {task['description']}")
            
            # 执行任务（通过 bot 调用 ACP）
            if self.bot and self.bot.acp_client:
                # 构建提示词
                prompt = f"这是一个定时任务，请执行以下内容并返回结果:\n\n{task['description']}"
                
                # 调用 ACP 获取结果
                result = self.bot.acp_client.chat(prompt, timeout=300)
                
                # 发送结果给用户
                chat_id = task['chat_id']
                
                # 格式化消息
                message = f"⏰ **定时任务提醒**\n\n任务: {task['description']}\n\n{result}"
                
                # 发送消息
                self.bot.reply_text(chat_id, message, streaming=False)
                
                self._log(f"任务 #{task_id} 执行完成，结果已发送")
            else:
                self._log(f"Bot 或 ACP 客户端不可用，任务 #{task_id} 执行失败")
                
        except Exception as e:
            self._log(f"执行任务 #{task_id} 失败: {e}")
            # 尝试发送错误信息
            try:
                if self.bot:
                    self.bot.reply_text(
                        task['chat_id'],
                        f"⏰ **定时任务执行失败**\n\n任务: {task['description']}\n\n错误: {str(e)}",
                        streaming=False
                    )
            except:
                pass
        
        finally:
            # 移除任务
            with self._lock:
                if task_id in self.tasks:
                    del self.tasks[task_id]
                if task_id in self._timers:
                    del self._timers[task_id]
            
            # 保存更新后的任务列表
            self._save_tasks()
    
    def create_task(self, chat_id: str, description: str, execute_time: float) -> int:
        """
        创建定时任务
        
        Args:
            chat_id: 聊天 ID
            description: 任务描述/指令
            execute_time: 执行时间（时间戳）
            
        Returns:
            task_id: 任务 ID
        """
        with self._lock:
            self.task_id_counter += 1
            task_id = self.task_id_counter
            
            self.tasks[task_id] = {
                'id': task_id,
                'chat_id': chat_id,
                'description': description,
                'execute_time': execute_time,
                'created_at': time.time(),
                'status': 'pending'
            }
        
        # 保存并调度
        self._save_tasks()
        self._schedule_task(task_id)
        
        self._log(f"创建任务 #{task_id}: {description}")
        return task_id
    
    def list_tasks(self, chat_id: str = None) -> List[dict]:
        """
        列出任务
        
        Args:
            chat_id: 如果指定，只返回该聊天的任务
            
        Returns:
            任务列表
        """
        with self._lock:
            tasks = []
            for task in self.tasks.values():
                if chat_id is None or task['chat_id'] == chat_id:
                    tasks.append(task.copy())
            return tasks
    
    def cancel_task(self, task_id: int) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功取消
        """
        with self._lock:
            if task_id not in self.tasks:
                return False
            
            # 取消定时器
            if task_id in self._timers:
                self._timers[task_id].cancel()
                del self._timers[task_id]
            
            # 移除任务
            del self.tasks[task_id]
        
        # 保存更新
        self._save_tasks()
        
        self._log(f"任务 #{task_id} 已取消")
        return True
    
    def shutdown(self):
        """关闭调度器，取消所有定时器"""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        
        self._log("调度器已关闭")


# 全局调度器实例
_scheduler: Optional[TaskScheduler] = None


def get_scheduler(bot_ref=None) -> TaskScheduler:
    """获取全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler(bot_ref)
    elif bot_ref is not None:
        # 更新 bot 引用
        _scheduler.bot = bot_ref
    return _scheduler


def parse_time(time_str: str) -> Optional[float]:
    """
    解析时间字符串为时间戳
    
    支持格式：
    - "明天上午9点"
    - "今天下午3点"
    - "10分钟后"
    - "1小时后"
    - "2024-01-15 09:00"
    """
    now = datetime.now()
    
    # 清理输入
    time_str = time_str.strip().lower()
    
    try:
        # 尝试解析绝对时间 (YYYY-MM-DD HH:MM)
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            return dt.timestamp()
        except ValueError:
            pass
        
        # 相对时间：X分钟后
        match = re.match(r'(\d+)\s*分钟后?', time_str)
        if match:
            minutes = int(match.group(1))
            dt = now + timedelta(minutes=minutes)
            return dt.timestamp()
        
        # 相对时间：X小时后
        match = re.match(r'(\d+)\s*小时后?', time_str)
        if match:
            hours = int(match.group(1))
            dt = now + timedelta(hours=hours)
            return dt.timestamp()
        
        # 相对时间：X天后
        match = re.match(r'(\d+)\s*天后?', time_str)
        if match:
            days = int(match.group(1))
            dt = now + timedelta(days=days)
            return dt.timestamp()
        
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
                # 时间已过，设为明天
                dt += timedelta(days=1)
            return dt.timestamp()
        
        # 不支持的时间格式
        return None
        
    except Exception as e:
        print(f"[SCHEDULER] 解析时间失败: {e}")
        return None


def format_task_list(tasks: List[dict]) -> str:
    """格式化任务列表为可读文本"""
    if not tasks:
        return "暂无定时任务"
    
    lines = ["📋 **定时任务列表**\n"]
    
    for task in sorted(tasks, key=lambda x: x['execute_time']):
        task_id = task['id']
        description = task['description']
        execute_time = task['execute_time']
        
        # 格式化时间
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
        
        lines.append(f"**#{task_id}** - {time_str} ({remaining_str})")
        lines.append(f"  内容: {description[:50]}{'...' if len(description) > 50 else ''}\n")
    
    return "\n".join(lines)
