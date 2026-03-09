#!/usr/bin/env python3
"""
CLI 客户端 - 通过 Unix Socket 与 Bot 交互

支持交互式聊天和单次命令
"""

import json
import socket
import sys
import os
from datetime import datetime


class CLIClient:
    """本地 CLI 客户端"""
    
    def __init__(self, socket_path: str = "/tmp/bot_cli.sock"):
        self.socket_path = socket_path
        self.chat_history = []
        
    def _send_request(self, command: str, params: dict = None) -> dict:
        """发送请求到 Bot"""
        if not os.path.exists(self.socket_path):
            return {'error': f'Bot CLI server not found at {self.socket_path}'}
        
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(30)  # 30秒超时
            sock.connect(self.socket_path)
            
            request = {
                'command': command,
                'params': params or {}
            }
            
            sock.send(json.dumps(request).encode('utf-8'))
            
            # 接收响应
            response_data = b''
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response_data += chunk
                
            sock.close()
            
            return json.loads(response_data.decode('utf-8'))
            
        except socket.timeout:
            return {'error': 'Request timeout'}
        except Exception as e:
            return {'error': str(e)}
            
    def chat(self, message: str, chat_id: str = 'cli_default') -> str:
        """发送聊天消息"""
        response = self._send_request('chat', {
            'message': message,
            'chat_id': chat_id
        })
        
        if 'error' in response:
            return f"[Error] {response['error']}"
        
        return response.get('message', '[No response]')
        
    def get_status(self) -> dict:
        """获取 Bot 状态"""
        return self._send_request('status')
        
    def get_tasks(self) -> dict:
        """获取定时任务"""
        return self._send_request('tasks')
        
    def interactive_mode(self):
        """交互式聊天模式"""
        print("=" * 60)
        print("🤖 Bot CLI 交互式聊天")
        print("=" * 60)
        print("命令:")
        print("  /status  - 查看 Bot 状态")
        print("  /tasks   - 查看定时任务")
        print("  /clear   - 清除聊天记录")
        print("  /quit    - 退出")
        print("=" * 60)
        print()
        
        while True:
            try:
                user_input = input("👤 You: ").strip()
                
                if not user_input:
                    continue
                    
                if user_input.lower() in ('/quit', '/exit', 'quit', 'exit'):
                    print("👋 再见！")
                    break
                    
                if user_input == '/status':
                    status = self.get_status()
                    print(f"\n📊 Bot 状态:")
                    for k, v in status.items():
                        print(f"  {k}: {v}")
                    print()
                    continue
                    
                if user_input == '/tasks':
                    tasks = self.get_tasks()
                    print(f"\n📋 定时任务:")
                    tasks_data = tasks.get('tasks', {})
                    if not tasks_data:
                        print("  (无任务)")
                    else:
                        for tid, task in tasks_data.items():
                            print(f"  #{tid}: {task.get('description', 'N/A')[:30]}... [{task.get('status')}]")
                    print()
                    continue
                    
                if user_input == '/clear':
                    self.chat_history.clear()
                    print("\n🗑️ 聊天记录已清除\n")
                    continue
                    
                # 添加用户消息到历史
                self.chat_history.append({'role': 'user', 'content': user_input, 'time': datetime.now().isoformat()})
                
                # 发送消息并获取回复
                print("🤖 Bot 思考中...")
                response = self.chat(user_input)
                
                # 添加 Bot 回复到历史
                self.chat_history.append({'role': 'bot', 'content': response, 'time': datetime.now().isoformat()})
                
                # 显示回复
                print(f"\n🤖 Bot: {response}\n")
                
            except KeyboardInterrupt:
                print("\n\n👋 再见！")
                break
            except Exception as e:
                print(f"\n❌ 错误: {e}\n")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Bot CLI 客户端')
    parser.add_argument('--socket', '-s', default='/tmp/bot_cli.sock', help='Socket 路径')
    parser.add_argument('command', nargs='?', help='命令 (chat/status/tasks)')
    parser.add_argument('message', nargs='?', help='消息内容')
    
    args = parser.parse_args()
    
    client = CLIClient(args.socket)
    
    # 无参数：交互模式
    if not args.command:
        client.interactive_mode()
        return
        
    # 单次命令模式
    if args.command == 'chat':
        if not args.message:
            # 从 stdin 读取
            print("输入消息 (Ctrl+D 结束):")
            message = sys.stdin.read().strip()
        else:
            message = args.message
            
        response = client.chat(message)
        print(response)
        
    elif args.command == 'status':
        status = client.get_status()
        print(json.dumps(status, indent=2))
        
    elif args.command == 'tasks':
        tasks = client.get_tasks()
        print(json.dumps(tasks, indent=2))
        
    else:
        # 直接作为聊天消息
        response = client.chat(args.command)
        print(response)


if __name__ == '__main__':
    main()
