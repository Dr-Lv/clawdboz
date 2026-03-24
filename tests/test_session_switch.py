#!/usr/bin/env python3
"""
会话切换并发测试
测试场景：快速切换会话并发送消息，验证消息不串流、无残留加载状态

测试步骤：
1. 创建3个独立的 WebSocket 连接（模拟3个浏览器标签页）
2. 同时在3个会话中发送消息（不等回复完成）
3. 等待所有消息生成完成
4. 检查：
   - 是否有多余回复消息气泡一直显示生成中
   - 消息回复是否串流

使用方法:
    python tests/test_session_switch.py
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import websockets


@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    messages: List[dict] = field(default_factory=list)
    responses: List[dict] = field(default_factory=list)
    start_received: bool = False
    done_received: bool = False
    chunks: List[str] = field(default_factory=list)
    error: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0


class SessionWorker:
    """会话工作器 - 每个会话一个独立的 WebSocket 连接"""
    
    def __init__(self, tester, session_id: str, ws_url: str, token: str):
        self.tester = tester
        self.session_id = session_id
        self.ws_url = ws_url
        self.token = token
        self.state = SessionState(session_id=session_id)
        self.ws = None
        self.message_to_send = None
        self.bot_id = None
        
    async def connect(self) -> bool:
        """建立 WebSocket 连接"""
        try:
            uri = f"{self.ws_url}?token={self.token}"
            self.ws = await websockets.connect(uri, ping_interval=None)
            self.tester.log(f"[{self.session_id}] WebSocket 连接成功")
            return True
        except Exception as e:
            self.tester.log(f"[{self.session_id}] WebSocket 连接失败: {e}", "FAIL")
            return False
    
    async def disconnect(self):
        """断开连接"""
        if self.ws:
            await self.ws.close()
            self.ws = None
    
    async def send_message(self, bot_id: str, message: str) -> bool:
        """发送消息"""
        if not self.ws:
            return False
        
        self.bot_id = bot_id
        self.state.start_time = time.time()
        
        request = {
            "mode": "single",
            "bots": [bot_id],
            "message": message,
            "chat_id": self.session_id
        }
        
        try:
            await self.ws.send(json.dumps(request))
            self.state.messages.append({
                "role": "user",
                "content": message,
                "time": time.time()
            })
            self.tester.log(f"[{self.session_id}] 发送消息: {message}")
            return True
        except Exception as e:
            self.tester.log(f"[{self.session_id}] 发送消息失败: {e}", "FAIL")
            return False
    
    async def receive_responses(self, timeout: float = 60.0) -> bool:
        """接收响应"""
        if not self.ws:
            return False
        
        start_time = time.time()
        
        try:
            while time.time() - start_time < timeout:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                    data = json.loads(msg)
                    
                    msg_type = data.get("type", "unknown")
                    
                    if msg_type == "start":
                        self.state.start_received = True
                        self.tester.log(f"[{self.session_id}] 收到 start")
                        
                    elif msg_type == "chunk":
                        content = data.get("content", "")
                        self.state.chunks.append(content)
                        # 只记录前50字符
                        preview = content[:50].replace('\n', ' ')
                        if len(content) > 50:
                            preview += "..."
                        self.tester.log(f"[{self.session_id}] 收到 chunk: {preview}")
                        
                    elif msg_type == "done":
                        self.state.done_received = True
                        self.state.end_time = time.time()
                        self.state.responses.append({
                            "role": "bot",
                            "content": data.get("final", ""),
                            "time": time.time()
                        })
                        duration = self.state.end_time - self.state.start_time
                        self.tester.log(f"[{self.session_id}] 收到 done (耗时: {duration:.2f}s)", "PASS")
                        return True
                        
                    elif msg_type == "error":
                        self.state.error = data.get("error", "Unknown error")
                        self.state.done_received = True
                        self.tester.log(f"[{self.session_id}] 收到错误: {self.state.error}", "FAIL")
                        return False
                        
                except asyncio.TimeoutError:
                    continue
                    
        except Exception as e:
            self.tester.log(f"[{self.session_id}] 接收异常: {e}", "FAIL")
            return False
        
        # 超时
        self.tester.log(f"[{self.session_id}] 响应超时", "FAIL")
        return False


class SessionSwitchTester:
    """会话切换测试工具"""
    
    def __init__(self, host: str = "localhost", port: int = 8080, token: str = ""):
        self.ws_url = f"ws://{host}:{port}/ws/chat"
        self.token = token
        self.workers: Dict[str, SessionWorker] = {}
        self.results = []
        
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        timestamp = time.strftime("%H:%M:%S")
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "ℹ️")
        print(f"[{timestamp}] {prefix} {message}")
        self.results.append({"time": timestamp, "level": level, "message": message})
    
    def check_message_interleaving(self) -> List[str]:
        """检查消息是否串流"""
        issues = []
        
        # 检查每个会话的 chunks 是否只包含该会话应该收到的内容
        for sid, worker in self.workers.items():
            state = worker.state
            if not state.chunks:
                continue
            
            full_content = "\n".join(state.chunks)
            
            # 检查是否包含其他会话的消息标识
            for other_sid, other_worker in self.workers.items():
                if other_sid == sid:
                    continue
                
                # 获取其他会话的用户消息
                for msg in other_worker.state.messages:
                    if msg.get("role") == "user":
                        user_content = msg.get("content", "")
                        # 如果回复中包含了其他会话的数字，可能是串流
                        if user_content in full_content:
                            issues.append(f"[{sid}] 的回复可能包含 [{other_sid}] 的内容: '{user_content}'")
        
        return issues
    
    def check_orphaned_loading(self) -> List[str]:
        """检查是否有多余的加载状态"""
        issues = []
        
        for sid, worker in self.workers.items():
            state = worker.state
            if state.start_received and not state.done_received:
                elapsed = time.time() - state.start_time if state.start_time else 0
                issues.append(f"[{sid}] 开始接收回复但未完成 (已等待 {elapsed:.1f}s)，可能残留加载状态")
        
        return issues
    
    def check_response_completeness(self) -> List[str]:
        """检查回复完整性"""
        issues = []
        
        for sid, worker in self.workers.items():
            state = worker.state
            
            if not state.messages:
                continue
            
            if not state.start_received:
                issues.append(f"[{sid}] 发送了消息但未收到 start")
            elif not state.done_received:
                issues.append(f"[{sid}] 收到了 start 但未收到 done")
            elif not state.responses:
                issues.append(f"[{sid}] 收到了 done 但没有回复内容")
        
        return issues
    
    async def run_test(self) -> bool:
        """运行完整的测试流程"""
        self.log("=" * 70)
        self.log("开始会话切换并发测试")
        self.log("=" * 70)
        
        # 创建3个会话工作器
        session_ids = [
            f"session_1_{int(time.time())}",
            f"session_2_{int(time.time())}",
            f"session_3_{int(time.time())}",
        ]
        
        messages = ["数字1", "数字2", "数字3"]
        
        # 步骤1: 创建所有会话连接
        self.log("\n▶ 步骤 1/5: 创建3个独立的 WebSocket 连接...")
        for sid in session_ids:
            worker = SessionWorker(self, sid, self.ws_url, self.token)
            if await worker.connect():
                self.workers[sid] = worker
            else:
                self.log(f"无法创建会话 {sid}，测试中止", "FAIL")
                return False
        
        # 步骤2: 同时在3个会话中发送消息
        self.log("\n▶ 步骤 2/5: 同时在3个会话中发送消息...")
        send_tasks = []
        for i, (sid, worker) in enumerate(self.workers.items()):
            task = worker.send_message("feishu-bot", messages[i])
            send_tasks.append(task)
        
        # 等待所有消息发送完成
        await asyncio.gather(*send_tasks)
        self.log("✓ 所有消息已发送")
        
        # 步骤3: 同时接收所有会话的响应
        self.log("\n▶ 步骤 3/5: 等待所有消息生成完成...")
        receive_tasks = []
        for worker in self.workers.values():
            task = worker.receive_responses(timeout=90.0)
            receive_tasks.append(task)
        
        # 等待所有响应完成
        await asyncio.gather(*receive_tasks, return_exceptions=True)
        self.log("✓ 所有响应接收完成")
        
        # 步骤4: 断开所有连接
        self.log("\n▶ 步骤 4/5: 断开所有连接...")
        disconnect_tasks = [w.disconnect() for w in self.workers.values()]
        await asyncio.gather(*disconnect_tasks)
        self.log("✓ 所有连接已断开")
        
        # 步骤5: 检查结果
        self.log("\n▶ 步骤 5/5: 检查结果...")
        
        issues = []
        
        # 检查1: 回复完整性
        completeness_issues = self.check_response_completeness()
        if completeness_issues:
            self.log("\n⚠️ 回复完整性问题:", "WARN")
            for issue in completeness_issues:
                self.log(f"  - {issue}", "WARN")
            issues.extend(completeness_issues)
        else:
            self.log("✓ 所有回复完整", "PASS")
        
        # 检查2: 是否有多余的加载状态
        orphaned_issues = self.check_orphaned_loading()
        if orphaned_issues:
            self.log("\n❌ 发现多余的加载状态:", "FAIL")
            for issue in orphaned_issues:
                self.log(f"  - {issue}", "FAIL")
            issues.extend(orphaned_issues)
        else:
            self.log("✓ 没有残留的加载状态", "PASS")
        
        # 检查3: 消息是否串流
        interleaving_issues = self.check_message_interleaving()
        if interleaving_issues:
            self.log("\n❌ 发现消息串流:", "FAIL")
            for issue in interleaving_issues:
                self.log(f"  - {issue}", "FAIL")
            issues.extend(interleaving_issues)
        else:
            self.log("✓ 没有消息串流", "PASS")
        
        # 输出测试报告
        self.log("\n" + "=" * 70)
        self.log("测试报告")
        self.log("=" * 70)
        
        total_sessions = len(self.workers)
        completed_sessions = sum(1 for w in self.workers.values() if w.state.done_received)
        
        self.log(f"\n会话统计:")
        self.log(f"  - 总会话数: {total_sessions}")
        self.log(f"  - 完成响应: {completed_sessions}")
        self.log(f"  - 发现问题: {len(issues)}")
        
        self.log(f"\n各会话详情:")
        for sid, worker in self.workers.items():
            state = worker.state
            status = "✅ 完成" if state.done_received else "❌ 未完成"
            duration = state.end_time - state.start_time if state.end_time else 0
            chunk_count = len(state.chunks)
            self.log(f"  - {sid}: {status}, {chunk_count} chunks, {duration:.2f}s")
        
        if issues:
            self.log(f"\n❌ 测试失败: 发现 {len(issues)} 个问题", "FAIL")
            return False
        else:
            self.log(f"\n✅ 测试通过: 所有检查项正常", "PASS")
            return True


async def main():
    """主函数"""
    # 检查依赖
    try:
        import websockets
    except ImportError:
        print("请先安装依赖: uv pip install websockets")
        sys.exit(1)
    
    # 创建测试器
    tester = SessionSwitchTester(
        host="localhost",
        port=8080,
        token="clawdboz-test-2024"
    )
    
    # 运行测试
    try:
        passed = await tester.run_test()
        sys.exit(0 if passed else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
