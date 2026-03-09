#!/usr/bin/env python3
"""
本地 CLI 服务器 - 为 Bot 提供双向命令行接口

使用 Unix Domain Socket 进行本地进程间通信
"""

import json
import os
import socket
import threading
import time
from typing import Optional, Callable


class CLIServer:
    """本地 CLI 服务器 - 通过 Unix Socket 接收命令"""
    
    def __init__(self, socket_path: str = "/tmp/bot_cli.sock", bot_ref=None):
        self.socket_path = socket_path
        self.bot_ref = bot_ref  # Bot 实例引用
        self.server_socket = None
        self.running = False
        self.thread = None
        
    def start(self):
        """启动 CLI 服务器"""
        # 清理旧的 socket 文件
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(5)
        self.running = True
        
        self.thread = threading.Thread(target=self._serve_loop, daemon=True)
        self.thread.start()
        
        print(f"[CLI] 服务器已启动: {self.socket_path}")
        
    def stop(self):
        """停止 CLI 服务器"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        print("[CLI] 服务器已停止")
        
    def _serve_loop(self):
        """服务循环"""
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                conn, addr = self.server_socket.accept()
                
                # 处理客户端连接
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(conn,),
                    daemon=True
                )
                client_thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[CLI] 服务错误: {e}")
                    
    def _handle_client(self, conn: socket.socket):
        """处理客户端请求"""
        try:
            # 接收数据
            data = conn.recv(65536).decode('utf-8')
            if not data:
                return
                
            request = json.loads(data)
            command = request.get('command')
            params = request.get('params', {})
            
            # 执行命令
            response = self._execute_command(command, params)
            
            # 发送响应
            conn.send(json.dumps(response).encode('utf-8'))
            
        except json.JSONDecodeError:
            conn.send(json.dumps({'error': 'Invalid JSON'}).encode('utf-8'))
        except Exception as e:
            conn.send(json.dumps({'error': str(e)}).encode('utf-8'))
        finally:
            conn.close()
            
    def _execute_command(self, command: str, params: dict) -> dict:
        """执行命令"""
        if command == 'chat':
            return self._cmd_chat(params)
        elif command == 'status':
            return self._cmd_status()
        elif command == 'tasks':
            return self._cmd_tasks()
        else:
            return {'error': f'Unknown command: {command}'}
            
    def _cmd_chat(self, params: dict) -> dict:
        """聊天命令 - 直接调用 Bot 处理消息"""
        message = params.get('message', '')
        chat_id = params.get('chat_id', 'cli_default')
        
        if not self.bot_ref:
            return {'error': 'Bot not available'}
        
        if not message:
            return {'error': 'Empty message'}
        
        try:
            # 创建模拟的消息数据
            from datetime import datetime
            
            # 构建 ACP 提示词
            prompt = f"用户消息: {message}\n\n请回复用户的消息。"
            
            # 调用 ACP 获取回复
            if self.bot_ref.acp_client is None:
                from .acp_client import ACPClient
                self.bot_ref.acp_client = ACPClient(bot_ref=self.bot_ref)
            
            # 执行聊天（同步调用）
            result = self.bot_ref.acp_client.chat(prompt, timeout=60)
            
            return {
                'success': True,
                'message': result,
                'chat_id': chat_id
            }
            
        except Exception as e:
            return {'error': str(e)}
            
    def _cmd_status(self) -> dict:
        """状态命令"""
        if not self.bot_ref:
            return {'error': 'Bot not available'}
        
        return {
            'app_id': self.bot_ref.app_id[:10] + '...' if self.bot_ref.app_id else None,
            'running': True,
            'processed_messages': len(self.bot_ref.processed_messages)
        }
        
    def _cmd_tasks(self) -> dict:
        """获取定时任务"""
        try:
            tasks_file = self.bot_ref._get_tasks_file_path()
            if os.path.exists(tasks_file):
                with open(tasks_file, 'r') as f:
                    data = json.load(f)
                return {'tasks': data.get('tasks', {})}
            return {'tasks': {}}
        except Exception as e:
            return {'error': str(e)}


class CLIServerPlugin:
    """Bot 插件 - 集成 CLI 服务器"""
    
    def __init__(self, bot_instance, socket_path: str = "/tmp/bot_cli.sock"):
        self.bot = bot_instance
        self.cli_server = CLIServer(socket_path, bot_instance)
        
    def enable(self):
        """启用 CLI 服务器"""
        self.cli_server.start()
        
    def disable(self):
        """禁用 CLI 服务器"""
        self.cli_server.stop()
