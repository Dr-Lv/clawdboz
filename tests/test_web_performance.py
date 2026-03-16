#!/usr/bin/env python3
"""
Web Chat 性能测试
测试并发连接、响应时间等性能指标

使用方法:
    python tests/test_web_performance.py
"""

import asyncio
import json
import os
import sys
import time
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp
import websockets


class PerformanceTester:
    """性能测试工具"""
    
    def __init__(self, host: str = "localhost", port: int = 8080, token: str = ""):
        self.base_url = f"http://{host}:{port}"
        self.ws_url = f"ws://{host}:{port}"
        self.token = token
        self.results = []
        
    def log(self, message: str):
        """记录日志"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    async def test_api_latency(self, iterations: int = 10) -> dict:
        """测试 API 延迟"""
        self.log(f"测试 API 延迟 ({iterations} 次请求)...")
        
        latencies = []
        async with aiohttp.ClientSession() as session:
            for i in range(iterations):
                start = time.time()
                async with session.get(
                    f"{self.base_url}/api/bots",
                    params={"token": self.token}
                ) as resp:
                    await resp.json()
                    latency = (time.time() - start) * 1000  # ms
                    latencies.append(latency)
        
        result = {
            "min": min(latencies),
            "max": max(latencies),
            "avg": statistics.mean(latencies),
            "median": statistics.median(latencies),
        }
        
        self.log(f"  最小: {result['min']:.2f}ms")
        self.log(f"  最大: {result['max']:.2f}ms")
        self.log(f"  平均: {result['avg']:.2f}ms")
        self.log(f"  中位数: {result['median']:.2f}ms")
        
        return result
    
    async def test_concurrent_connections(self, count: int = 10) -> bool:
        """测试并发 WebSocket 连接"""
        self.log(f"测试并发连接 ({count} 个)...")
        
        connected = []
        failed = []
        
        async def try_connect(idx):
            try:
                uri = f"{self.ws_url}/ws/chat?token={self.token}"
                async with websockets.connect(uri, ping_interval=None) as ws:
                    connected.append(idx)
                    await asyncio.sleep(1)  # 保持连接1秒
            except Exception as e:
                failed.append((idx, str(e)))
        
        await asyncio.gather(*[try_connect(i) for i in range(count)])
        
        self.log(f"  成功: {len(connected)}/{count}")
        if failed:
            self.log(f"  失败: {len(failed)}")
        
        return len(connected) == count
    
    async def test_message_throughput(self, message_count: int = 10) -> dict:
        """测试消息吞吐量"""
        self.log(f"测试消息吞吐量 ({message_count} 条消息)...")
        
        uri = f"{self.ws_url}/ws/chat?token={self.token}"
        
        start_time = time.time()
        responses = 0
        
        async with websockets.connect(uri, ping_interval=None) as ws:
            # 发送消息
            for i in range(message_count):
                request = {
                    "mode": "single",
                    "bots": ["feishu-bot"],
                    "message": f"测试消息 {i}",
                    "chat_id": f"perf_test_{i}"
                }
                await ws.send(json.dumps(request))
            
            # 等待响应
            timeout = time.time() + 60
            while time.time() < timeout and responses < message_count:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    if data.get("type") == "done":
                        responses += 1
                except asyncio.TimeoutError:
                    break
        
        duration = time.time() - start_time
        throughput = responses / duration if duration > 0 else 0
        
        result = {
            "sent": message_count,
            "received": responses,
            "duration": duration,
            "throughput": throughput,
        }
        
        self.log(f"  发送: {message_count}")
        self.log(f"  接收: {responses}")
        self.log(f"  耗时: {duration:.2f}s")
        self.log(f"  吞吐量: {throughput:.2f} msg/s")
        
        return result
    
    async def run_all_tests(self):
        """运行所有性能测试"""
        self.log("=" * 60)
        self.log("开始 Web Chat 性能测试")
        self.log("=" * 60)
        
        # API 延迟测试
        self.log("")
        api_latency = await self.test_api_latency(iterations=10)
        
        # 并发连接测试
        self.log("")
        concurrent_ok = await self.test_concurrent_connections(count=5)
        
        # 消息吞吐量测试
        self.log("")
        throughput = await self.test_message_throughput(message_count=3)
        
        # 报告
        self.log("")
        self.log("=" * 60)
        self.log("性能测试报告")
        self.log("=" * 60)
        self.log(f"API 平均延迟: {api_latency['avg']:.2f}ms")
        self.log(f"并发连接: {'✓ 通过' if concurrent_ok else '✗ 失败'}")
        self.log(f"消息吞吐量: {throughput['throughput']:.2f} msg/s")
        self.log("=" * 60)


async def main():
    tester = PerformanceTester(
        host="localhost",
        port=8080,
        token="clawdboz-test-2024"
    )
    await tester.run_all_tests()


if __name__ == "__main__":
    try:
        import aiohttp
        import websockets
    except ImportError:
        print("请先安装依赖: uv pip install aiohttp websockets")
        sys.exit(1)
    
    asyncio.run(main())
