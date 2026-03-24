#!/usr/bin/env python3
"""
端到端测试 (E2E Test)
测试完整的 Web Chat 流程
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

# 配置
TEST_PORT = 18765
TEST_TOKEN = "e2e-test-token-12345"
BASE_URL = f"http://localhost:{TEST_PORT}"
WS_URL = f"ws://localhost:{TEST_PORT}/ws/chat?token={TEST_TOKEN}"


def start_server():
    """启动测试服务器"""
    print("[E2E] 启动测试服务器...")
    
    # 创建测试脚本
    test_script = """
import sys
sys.path.insert(0, '.')

from clawdboz import BotManager
from clawdboz.web import start_web_chat

# 创建 Manager
manager = BotManager(base_workplace='TEST_WORKPLACE_E2E')

# 注册 Mock Bot（不需要真实飞书凭证）
try:
    manager.register("bot-a", "cli_test_a", "secret_a")
    manager.register("bot-b", "cli_test_b", "secret_b")
    print("[E2E Server] Bots registered")
except Exception as e:
    print(f"[E2E Server] Bot register error (expected): {e}")

# 启动 Web 服务（阻塞）
start_web_chat(manager.bots, port={port}, auth_token="{token}")
""".format(port=TEST_PORT, token=TEST_TOKEN)
    
    # 写入临时脚本
    script_path = tempfile.mktemp(suffix=".py")
    with open(script_path, "w") as f:
        f.write(test_script)
    
    # 启动服务器进程
    proc = subprocess.Popen(
        [sys.executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    
    # 等待服务器启动
    time.sleep(3)
    
    return proc, script_path


def test_http_api():
    """测试 HTTP API"""
    print("\n[E2E] 测试 HTTP API...")
    
    # 测试根路径
    try:
        with urllib.request.urlopen(f"{BASE_URL}/", timeout=5) as r:
            data = json.loads(r.read().decode())
            assert data["name"] == "Clawdboz Web Chat"
            print("  ✓ GET /")
    except Exception as e:
        print(f"  ✗ GET / failed: {e}")
        return False
    
    # 测试 Bot 列表
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/bots", timeout=5) as r:
            data = json.loads(r.read().decode())
            assert "bots" in data
            print(f"  ✓ GET /api/bots ({len(data['bots'])} bots)")
    except Exception as e:
        print(f"  ✗ GET /api/bots failed: {e}")
        return False
    
    return True


def test_websocket():
    """测试 WebSocket"""
    print("\n[E2E] 测试 WebSocket...")
    
    try:
        import websocket
    except ImportError:
        print("  ⚠ websocket-client 未安装，跳过 WebSocket 测试")
        print("     pip install websocket-client")
        return True
    
    try:
        ws = websocket.create_connection(WS_URL, timeout=10)
        print("  ✓ WebSocket 连接成功")
        
        # 测试单聊
        print("\n  [测试] 单聊模式...")
        ws.send(json.dumps({
            "mode": "single",
            "bots": ["bot-a"],
            "message": "Hello"
        }))
        
        responses = []
        start_time = time.time()
        while time.time() - start_time < 10:  # 最多等10秒
            try:
                ws.settimeout(1)
                msg = json.loads(ws.recv())
                responses.append(msg)
                print(f"    ← {msg['type']}")
                
                if msg["type"] == "done":
                    break
                if msg["type"] == "error":
                    print(f"    Error: {msg.get('error')}")
                    break
            except websocket.WebSocketTimeoutException:
                continue
        
        # 验证消息序列
        types = [r["type"] for r in responses]
        assert "start" in types, "缺少 start 消息"
        assert "done" in types or "error" in types, "缺少 done/error 消息"
        print("  ✓ 单聊消息序列正确")
        
        ws.close()
        return True
        
    except Exception as e:
        print(f"  ✗ WebSocket 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_static_files():
    """测试静态文件"""
    print("\n[E2E] 测试静态文件...")
    
    try:
        with urllib.request.urlopen(
            f"{BASE_URL}/static/index.html?token={TEST_TOKEN}", 
            timeout=5
        ) as r:
            content = r.read().decode()
            assert "Clawdboz Web Chat" in content
            print("  ✓ index.html 可访问")
            return True
    except Exception as e:
        print(f"  ✗ 静态文件测试失败: {e}")
        return False


def cleanup(proc, script_path):
    """清理"""
    print("\n[E2E] 清理...")
    proc.terminate()
    proc.wait()
    
    if os.path.exists(script_path):
        os.remove(script_path)
    
    # 清理测试目录
    import shutil
    if os.path.exists("TEST_WORKPLACE_E2E"):
        shutil.rmtree("TEST_WORKPLACE_E2E")
    
    print("  ✓ 清理完成")


def main():
    """主测试流程"""
    print("="*60)
    print("Clawdboz Web Chat E2E 测试")
    print("="*60)
    
    proc = None
    script_path = None
    
    try:
        # 启动服务器
        proc, script_path = start_server()
        
        # 等待服务器就绪
        print("\n[E2E] 等待服务器就绪...")
        time.sleep(2)
        
        # 运行测试
        results = []
        
        results.append(("HTTP API", test_http_api()))
        results.append(("静态文件", test_static_files()))
        results.append(("WebSocket", test_websocket()))
        
        # 输出结果
        print("\n" + "="*60)
        print("测试结果")
        print("="*60)
        
        for name, passed in results:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status} {name}")
        
        all_passed = all(r[1] for r in results)
        
        print("="*60)
        if all_passed:
            print("✓ 所有测试通过！")
        else:
            print("✗ 部分测试失败")
        print("="*60)
        
        return 0 if all_passed else 1
        
    except KeyboardInterrupt:
        print("\n[E2E] 用户中断")
        return 1
    except Exception as e:
        print(f"\n[E2E] 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if proc:
            cleanup(proc, script_path)


if __name__ == "__main__":
    sys.exit(main())
