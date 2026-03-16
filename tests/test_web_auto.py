#!/usr/bin/env python3
"""
Web Chat 自动化测试脚本
基于 test-driven-development skill 和 verification-before-completion skill

测试覆盖:
1. HTTP API 端点
2. WebSocket 连接和消息流
3. 单聊/群聊功能
4. 文件上传
5. Token 鉴权

使用方法:
    # 运行所有测试
    python tests/test_web_auto.py
    
    # 运行特定测试
    python tests/test_web_auto.py TestWebChatAuto.test_bots_api
    
    # 详细输出
    python tests/test_web_auto.py -v
"""

import asyncio
import json
import os
import sys
import time
import unittest
import websockets
from typing import Dict, List, Optional

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试配置
TEST_CONFIG = {
    "host": "localhost",
    "port": 8080,
    "token": "clawdboz-test-2024",
    "timeout": 30,  # 测试超时时间(秒)
}


class WebChatTester:
    """Web Chat 测试工具类"""
    
    def __init__(self, host: str = "localhost", port: int = 8080, token: str = ""):
        self.base_url = f"http://{host}:{port}"
        self.ws_url = f"ws://{host}:{port}"
        self.token = token
        self.results = []
        
    def log(self, message: str, level: str = "INFO"):
        """记录测试日志"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
        self.results.append({"time": timestamp, "level": level, "message": message})
    
    async def test_http_health(self) -> bool:
        """测试 HTTP 服务健康状态"""
        import aiohttp
        
        self.log("测试 HTTP 健康检查...")
        try:
            async with aiohttp.ClientSession() as session:
                # 测试静态文件
                async with session.get(
                    f"{self.base_url}/static/index.html",
                    params={"token": self.token},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        self.log(f"✓ 静态文件服务正常 (HTTP {resp.status})")
                        return True
                    else:
                        self.log(f"✗ 静态文件服务异常 (HTTP {resp.status})", "ERROR")
                        return False
        except Exception as e:
            self.log(f"✗ HTTP 健康检查失败: {e}", "ERROR")
            return False
    
    async def test_bots_api(self) -> bool:
        """测试 Bot 列表 API"""
        import aiohttp
        
        self.log("测试 /api/bots 接口...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/bots",
                    params={"token": self.token},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bots = data.get("bots", [])
                        self.log(f"✓ Bot 列表 API 正常，发现 {len(bots)} 个 Bot")
                        for bot in bots:
                            self.log(f"  - {bot['id']}: {bot.get('name', 'N/A')}")
                        return len(bots) > 0
                    else:
                        self.log(f"✗ Bot 列表 API 异常 (HTTP {resp.status})", "ERROR")
                        return False
        except Exception as e:
            self.log(f"✗ Bot 列表 API 测试失败: {e}", "ERROR")
            return False
    
    async def test_websocket_connection(self) -> bool:
        """测试 WebSocket 连接"""
        self.log("测试 WebSocket 连接...")
        try:
            uri = f"{self.ws_url}/ws/chat?token={self.token}"
            async with websockets.connect(uri, ping_interval=None) as ws:
                self.log("✓ WebSocket 连接成功")
                return True
        except Exception as e:
            self.log(f"✗ WebSocket 连接失败: {e}", "ERROR")
            return False
    
    async def test_single_chat(self, bot_id: str = "feishu-bot", message: str = "你好") -> bool:
        """测试单聊功能"""
        self.log(f"测试单聊功能 (Bot: {bot_id})...")
        
        try:
            uri = f"{self.ws_url}/ws/chat?token={self.token}"
            async with websockets.connect(uri, ping_interval=None) as ws:
                # 发送消息
                request = {
                    "mode": "single",
                    "bots": [bot_id],
                    "message": message,
                    "chat_id": f"test_chat_{int(time.time())}"
                }
                await ws.send(json.dumps(request))
                self.log(f"  → 发送: {message}")
                
                # 等待响应
                responses = []
                start_time = time.time()
                
                while time.time() - start_time < 30:  # 最多等待30秒
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        data = json.loads(msg)
                        responses.append(data)
                        
                        if data.get("type") == "start":
                            self.log(f"  ← 收到 start")
                        elif data.get("type") == "chunk":
                            content = data.get("content", "")[:50]
                            if len(data.get("content", "")) > 50:
                                content += "..."
                            self.log(f"  ← 收到 chunk: {content}")
                        elif data.get("type") == "done":
                            self.log(f"  ← 收到 done ✓")
                            return True
                        elif data.get("type") == "error":
                            self.log(f"  ← 收到错误: {data.get('error')}", "ERROR")
                            return False
                    except asyncio.TimeoutError:
                        continue
                
                self.log("✗ 单聊测试超时", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"✗ 单聊测试失败: {e}", "ERROR")
            return False
    
    async def test_group_chat(self, bot_ids: List[str], message: str = "大家好") -> bool:
        """测试群聊功能"""
        self.log(f"测试群聊功能 (Bots: {', '.join(bot_ids)})...")
        
        try:
            uri = f"{self.ws_url}/ws/chat?token={self.token}"
            async with websockets.connect(uri, ping_interval=None) as ws:
                # 发送群聊消息（需要@某个Bot才会回复）
                mention = f"@{bot_ids[0]} " if bot_ids else ""
                request = {
                    "mode": "group",
                    "bots": bot_ids,
                    "message": f"{mention}{message}",
                    "chat_id": f"test_group_{int(time.time())}"
                }
                await ws.send(json.dumps(request))
                self.log(f"  → 发送: {request['message']}")
                
                # 等待响应
                responses = []
                start_time = time.time()
                
                while time.time() - start_time < 30:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        data = json.loads(msg)
                        responses.append(data)
                        
                        if data.get("type") == "start":
                            self.log(f"  ← [{data.get('bot_id')}] start")
                        elif data.get("type") == "done":
                            self.log(f"  ← [{data.get('bot_id')}] done ✓")
                            # 所有 Bot 都回复完成
                            if len([r for r in responses if r.get("type") == "done"]) >= len(bot_ids):
                                return True
                        elif data.get("type") == "error":
                            self.log(f"  ← 错误: {data.get('error')}", "ERROR")
                            return False
                    except asyncio.TimeoutError:
                        continue
                
                self.log("✗ 群聊测试超时", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"✗ 群聊测试失败: {e}", "ERROR")
            return False
    
    async def test_file_upload(self, file_path: str) -> bool:
        """测试文件上传功能"""
        import aiohttp
        
        self.log(f"测试文件上传 ({file_path})...")
        
        if not os.path.exists(file_path):
            self.log(f"✗ 文件不存在: {file_path}", "ERROR")
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file',
                             open(file_path, 'rb'),
                             filename=os.path.basename(file_path))
                
                async with session.post(
                    f"{self.base_url}/api/upload",
                    params={"token": self.token},
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("success"):
                            self.log(f"✓ 文件上传成功: {result.get('file_name')}")
                            return True
                        else:
                            self.log(f"✗ 文件上传失败: {result.get('error')}", "ERROR")
                            return False
                    else:
                        self.log(f"✗ 文件上传失败 (HTTP {resp.status})", "ERROR")
                        return False
        except Exception as e:
            self.log(f"✗ 文件上传测试失败: {e}", "ERROR")
            return False
    
    async def test_token_auth(self) -> bool:
        """测试 Token 鉴权"""
        self.log("测试 Token 鉴权...")
        
        tests = [
            ("正确 Token", self.token, True),
            ("错误 Token", "wrong-token", False),
            ("空 Token", "", False),
        ]
        
        all_passed = True
        for name, token, should_succeed in tests:
            try:
                uri = f"{self.ws_url}/ws/chat?token={token}"
                async with websockets.connect(uri, ping_interval=None) as ws:
                    if should_succeed:
                        self.log(f"  ✓ [{name}] 连接成功（符合预期）")
                    else:
                        self.log(f"  ✗ [{name}] 连接成功（不符合预期，应该失败）", "ERROR")
                        all_passed = False
            except Exception as e:
                if not should_succeed:
                    self.log(f"  ✓ [{name}] 连接失败（符合预期）")
                else:
                    self.log(f"  ✗ [{name}] 连接失败（不符合预期）: {e}", "ERROR")
                    all_passed = False
        
        return all_passed
    
    async def run_all_tests(self) -> Dict:
        """运行所有测试"""
        self.log("=" * 60)
        self.log("开始 Web Chat 自动化测试")
        self.log("=" * 60)
        
        start_time = time.time()
        results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "details": []
        }
        
        tests = [
            ("HTTP 健康检查", self.test_http_health),
            ("Bot 列表 API", self.test_bots_api),
            ("Token 鉴权", self.test_token_auth),
            ("WebSocket 连接", self.test_websocket_connection),
            ("单聊功能", lambda: self.test_single_chat("feishu-bot", "你好")),
            ("群聊功能", lambda: self.test_group_chat(["feishu-bot"], "测试群聊")),
        ]
        
        for test_name, test_func in tests:
            self.log("")
            self.log(f"▶ 运行测试: {test_name}")
            try:
                result = await test_func()
                results["total"] += 1
                if result:
                    results["passed"] += 1
                    results["details"].append({"name": test_name, "status": "PASS"})
                else:
                    results["failed"] += 1
                    results["details"].append({"name": test_name, "status": "FAIL"})
            except Exception as e:
                results["total"] += 1
                results["failed"] += 1
                results["details"].append({"name": test_name, "status": "ERROR", "error": str(e)})
                self.log(f"✗ 测试异常: {e}", "ERROR")
        
        duration = time.time() - start_time
        
        # 输出测试报告
        self.log("")
        self.log("=" * 60)
        self.log("测试报告")
        self.log("=" * 60)
        self.log(f"总测试数: {results['total']}")
        self.log(f"通过: {results['passed']} ✓")
        self.log(f"失败: {results['failed']} ✗")
        self.log(f"耗时: {duration:.2f} 秒")
        self.log("")
        
        for detail in results["details"]:
            status_icon = "✓" if detail["status"] == "PASS" else "✗"
            self.log(f"  {status_icon} {detail['name']}: {detail['status']}")
        
        self.log("=" * 60)
        
        return results


async def main():
    """主函数"""
    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    
    # 创建测试器
    tester = WebChatTester(
        host=TEST_CONFIG["host"],
        port=TEST_CONFIG["port"],
        token=TEST_CONFIG["token"]
    )
    
    # 运行所有测试
    results = await tester.run_all_tests()
    
    # 返回退出码
    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    # 检查依赖
    try:
        import aiohttp
        import websockets
    except ImportError:
        print("[安装依赖] 正在安装 aiohttp 和 websockets...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "aiohttp", "websockets"])
        print("[安装完成] 请重新运行测试")
        sys.exit(0)
    
    # 运行测试
    asyncio.run(main())
