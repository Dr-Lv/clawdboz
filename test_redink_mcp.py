#!/usr/bin/env python3
"""测试 Redink MCP 服务调用时的消息卡片更新频率"""
import sys
import time
sys.path.insert(0, '.')
from clawdboz import LarkBot

# 创建 bot 实例
bot = LarkBot('cli_a90ded6b63f89cd6', '3WDKvIVUHPYVXbEVYjRgRg2wORBDb5z3')

# 测试群聊 ID
chat_id = 'oc_d24a689f16656bb78b5a6b75c5a2b552'

# 测试调用 Redink MCP 服务的消息
test_msg = '调用redink mcp服务，生成一个ai失业的文案'

print('=' * 60)
print('测试 Redink MCP 服务调用时的流式更新')
print('=' * 60)
print(f'消息: {test_msg}')
print()

# 清空日志
open('bot_debug.log', 'w').close()

# 调用流式方法
start_time = time.time()
bot.run_msg_script_streaming(chat_id, test_msg)

# 等待完成
print()
print('等待 30 秒让操作完成（Redink 生成可能需要较长时间）...')
time.sleep(30)

# 分析更新频率
print()
print('=' * 60)
print('更新频率分析')
print('=' * 60)

# 读取日志分析
with open('bot_debug.log', 'r') as f:
    lines = f.readlines()

# 提取更新时间和字数
import re
updates = []
for line in lines:
    match = re.search(r'\[(\d{2}):(\d{2}):(\d{2})\].*更新卡片成功 \((\d+)字', line)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        chars = int(match.group(4))
        updates.append((f'{h:02d}:{m:02d}:{s:02d}', chars))

if len(updates) >= 2:
    print(f'总共更新了 {len(updates)} 次')
    print()
    print('各次更新详情:')
    
    total_time = 0
    for i in range(len(updates)):
        if i == 0:
            print(f'  {updates[i][0]}: {updates[i][1]}字 (初始)')
        else:
            # 解析时间差
            prev_parts = updates[i-1][0].split(':')
            curr_parts = updates[i][0].split(':')
            prev_sec = int(prev_parts[0]) * 3600 + int(prev_parts[1]) * 60 + int(prev_parts[2])
            curr_sec = int(curr_parts[0]) * 3600 + int(curr_parts[1]) * 60 + int(curr_parts[2])
            interval = curr_sec - prev_sec
            added = updates[i][1] - updates[i-1][1]
            total_time += interval
            print(f'  {updates[i][0]}: {updates[i][1]}字 (+{added}字, 间隔{interval}秒)')
    
    avg_interval = total_time / (len(updates) - 1)
    print()
    print(f'总耗时: {total_time}秒')
    print(f'平均更新间隔: {avg_interval:.2f}秒')
else:
    print('更新次数不足，无法分析间隔')

print()
print('测试完成')
