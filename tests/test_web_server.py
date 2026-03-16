#!/usr/bin/env python3
"""
WebChatServer 单元测试
"""

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 跳过测试如果 fastapi 未安装
try:
    from fastapi.testclient import TestClient
    from clawdboz.web.server import WebChatServer
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False
    print("[SKIP] fastapi 未安装，跳过 WebServer 测试")


@unittest.skipUnless(HAS_DEPS, "需要 fastapi")
class TestWebChatServer(unittest.TestCase):
    """WebChatServer 测试用例"""
    
    def setUp(self):
        """设置测试环境"""
        # 创建 Mock Bot
        self.mock_bot1 = Mock()
        self.mock_bot1._bot_id = "bot1"
        self.mock_bot1._work_dir = "/tmp/bot1"
        
        self.mock_bot2 = Mock()
        self.mock_bot2._bot_id = "bot2"
        self.mock_bot2._work_dir = "/tmp/bot2"
        
        self.bots = {
            "bot1": self.mock_bot1,
            "bot2": self.mock_bot2
        }
        
        # 创建服务器
        self.server = WebChatServer(
            self.bots,
            port=9999,
            auth_token="test-token-123"
        )
        self.client = TestClient(self.server.app)
    
    def test_root_endpoint(self):
        """测试根路径"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["name"], "Clawdboz Web Chat")
        self.assertIn("bot1", data["bots"])
        self.assertIn("bot2", data["bots"])
    
    def test_list_bots_endpoint(self):
        """测试 Bot 列表 API"""
        response = self.client.get("/api/bots")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("bots", data)
        self.assertEqual(len(data["bots"]), 2)
        
        bot_ids = [b["id"] for b in data["bots"]]
        self.assertIn("bot1", bot_ids)
        self.assertIn("bot2", bot_ids)
    
    def test_websocket_auth_success(self):
        """测试 WebSocket 鉴权成功"""
        with self.client.websocket_connect("/ws/chat?token=test-token-123") as ws:
            # 连接应成功建立
            pass
    
    def test_websocket_auth_failure(self):
        """测试 WebSocket 鉴权失败"""
        with self.client.websocket_connect("/ws/chat?token=wrong-token") as ws:
            # 应该收到关闭消息
            with self.assertRaises(Exception):
                ws.receive_text()
    
    def test_websocket_missing_token(self):
        """测试 WebSocket 缺少 Token"""
        with self.client.websocket_connect("/ws/chat") as ws:
            with self.assertRaises(Exception):
                ws.receive_text()


@unittest.skipUnless(HAS_DEPS, "需要 fastapi")
class TestWebSocketProtocol(unittest.TestCase):
    """测试 WebSocket 消息协议"""
    
    def setUp(self):
        """设置"""
        self.mock_bot = Mock()
        self.mock_bot._bot_id = "test-bot"
        self.mock_bot._work_dir = "/tmp/test"
        
        # 模拟 ACP 客户端
        mock_acp = Mock()
        def mock_chat(message, on_chunk=None, timeout=None):
            if on_chunk:
                on_chunk("Hello ")
                on_chunk("World!")
            return "Hello World!"
        mock_acp.chat = mock_chat
        self.mock_bot.acp_client = mock_acp
        
        self.server = WebChatServer(
            {"test": self.mock_bot},
            auth_token="token"
        )
        self.client = TestClient(self.server.app)
    
    def test_single_chat_message_sequence(self):
        """测试单聊消息序列"""
        with self.client.websocket_connect("/ws/chat?token=token") as ws:
            # 发送消息
            ws.send_json({
                "mode": "single",
                "bots": ["test"],
                "message": "Hi"
            })
            
            # 应收到 start
            msg1 = ws.receive_json()
            self.assertEqual(msg1["type"], "start")
            self.assertEqual(msg1["bot_id"], "test")
            self.assertIn("msg_id", msg1)
            self.assertIn("seq", msg1)
            
            # 应收到 chunk（可能有多个）
            chunks = []
            while True:
                msg = ws.receive_json()
                if msg["type"] == "chunk":
                    chunks.append(msg)
                    self.assertIn("content", msg)
                    self.assertIn("seq", msg)
                    # seq 应递增
                    if len(chunks) > 1:
                        self.assertGreater(msg["seq"], chunks[-2]["seq"])
                elif msg["type"] == "done":
                    self.assertEqual(msg["bot_id"], "test")
                    self.assertEqual(msg["final"], "Hello World!")
                    break
                else:
                    self.fail(f"意外的消息类型: {msg['type']}")
    
    def test_group_chat_multiple_bots(self):
        """测试群聊多个 Bot"""
        # 添加第二个 Bot
        mock_bot2 = Mock()
        mock_bot2._bot_id = "bot2"
        mock_bot2._work_dir = "/tmp/bot2"
        mock_acp2 = Mock()
        def mock_chat2(message, on_chunk=None, timeout=None):
            if on_chunk:
                on_chunk("Response ")
                on_chunk("from Bot2")
            return "Response from Bot2"
        mock_acp2.chat = mock_chat2
        mock_bot2.acp_client = mock_acp2
        
        server = WebChatServer(
            {"bot1": self.mock_bot, "bot2": mock_bot2},
            auth_token="token"
        )
        client = TestClient(server.app)
        
        with client.websocket_connect("/ws/chat?token=token") as ws:
            ws.send_json({
                "mode": "group",
                "bots": ["bot1", "bot2"],
                "message": "Hello"
            })
            
            # 应收到两个 start（顺序不确定）
            bot_starts = set()
            for _ in range(2):
                msg = ws.receive_json()
                self.assertEqual(msg["type"], "start")
                bot_starts.add(msg["bot_id"])
            
            self.assertEqual(bot_starts, {"bot1", "bot2"})
    
    def test_missing_parameters(self):
        """测试缺少参数"""
        with self.client.websocket_connect("/ws/chat?token=token") as ws:
            # 缺少 bots
            ws.send_json({
                "mode": "single",
                "message": "Hi"
            })
            
            msg = ws.receive_json()
            self.assertEqual(msg["type"], "error")
            self.assertIn("缺少必要参数", msg["error"])
    
    def test_nonexistent_bot(self):
        """测试不存在的 Bot"""
        with self.client.websocket_connect("/ws/chat?token=token") as ws:
            ws.send_json({
                "mode": "single",
                "bots": ["nonexistent"],
                "message": "Hi"
            })
            
            msg = ws.receive_json()
            self.assertEqual(msg["type"], "error")
            self.assertIn("不存在", msg["error"])


def quick_test():
    """快速测试"""
    if not HAS_DEPS:
        print("[SKIP] 缺少依赖，跳过快速测试")
        return
    
    print("\n" + "="*50)
    print("WebServer 快速测试")
    print("="*50 + "\n")
    
    # 创建 Mock
    mock_bot = Mock()
    mock_bot._bot_id = "test"
    mock_bot._work_dir = "/tmp"
    mock_bot.acp_client = None
    
    server = WebChatServer(
        {"test": mock_bot},
        port=8888,
        auth_token="demo-token"
    )
    
    client = TestClient(server.app)
    
    # 测试根路径
    print("[测试] GET /")
    r = client.get("/")
    print(f"  Status: {r.status_code}")
    print(f"  Data: {r.json()}")
    
    # 测试 Bot 列表
    print("\n[测试] GET /api/bots")
    r = client.get("/api/bots")
    print(f"  Status: {r.status_code}")
    print(f"  Bots: {r.json()['bots']}")
    
    print("\n" + "="*50)
    print("✓ 快速测试通过")
    print("="*50)


if __name__ == "__main__":
    quick_test()
    
    if HAS_DEPS:
        print("\n运行 unittest...\n")
        unittest.main(verbosity=2, exit=False)
    else:
        print("\n跳过 unittest（缺少依赖）")
