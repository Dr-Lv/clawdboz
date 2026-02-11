#!/usr/bin/env python3
"""测试 MCP 服务调用时的消息卡片更新频率"""
import sys
import time
sys.path.insert(0, '.')
from clawdboz import LarkBot

# 创建 bot 实例
bot = LarkBot('cli_a90ded6b63f89cd6', '3WDKvIVUHPYVXbEVYjRgRg2wORBDb5z3')

# 测试群聊 ID
chat_id = 'oc_d24a689f16656bb78b5a6b75c5a2b552'

# 测试调用 MCP 服务的消息（使用 Shell 工具）
test_msg = '执行 ls -la 命令查看当前目录'

print('=' * 60)
print('测试 MCP 服务调用时的流式更新')
print('=' * 60)
print(f'消息: {test_msg}')
print()

# 清空日志
import os
open('bot_debug.log', 'w').close()

# 调用流式方法
start_time = time.time()
bot.run_msg_script_streaming(chat_id, test_msg)

# 等待完成
print()
print('等待 15 秒让操作完成...')
time.sleep(15)

# 分析更新频率
print()
print('=' * 60)
print('更新频率分析')
print('=' * 60)

# 读取日志分析
with open('bot_debug.log', 'r') as f:
    lines = f.readlines()

# 提取 on_chunk 调用时间
import re
chunk_times = []
for line in lines:
    match = re.search(r'\[(\d{2}):(\d{2}):(\d{2})\].*\[on_chunk\] 被调用', line)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        chunk_times.append(h * 3600 + m * 60 + s)

if len(chunk_times) >= 2:
    print(f'总共更新了 {len(chunk_times)} 次')
    print()
    print('各次更新间隔:')
    for i in range(1, len(chunk_times)):
        interval = chunk_times[i] - chunk_times[i-1]
        print(f'  第{i}次 → 第{i+1}次: {interval}秒')
    
    avg_interval = sum(chunk_times[i] - chunk_times[i-1] for i in range(1, len(chunk_times))) / (len(chunk_times) - 1)
    print()
    print(f'平均更新间隔: {avg_interval:.2f}秒')
else:
    print('更新次数不足，无法分析间隔')

print()
print('测试完成')
