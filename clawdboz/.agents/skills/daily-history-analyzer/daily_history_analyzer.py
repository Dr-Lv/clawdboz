#!/usr/bin/env python3
"""
每日 HISTORY 对话分析器 (Skill 版本)
读取前一天的 HISTORY 文件，提取重要信息保存到记忆中，并生成报告到 assets 目录
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 添加 local-memory 模块路径
_local_memory_path = os.path.join(os.path.dirname(__file__), '..', 'local-memory')
_local_memory_path = os.path.abspath(_local_memory_path)
if _local_memory_path not in sys.path and os.path.exists(_local_memory_path):
    sys.path.insert(0, _local_memory_path)


def get_project_root() -> Path:
    """获取项目根目录（从 skill 目录向上 3 层）"""
    skill_dir = Path(__file__).resolve().parent
    return skill_dir.parent.parent.parent

from local_memory import MemoryManager


def get_skill_dir() -> str:
    """获取本 skill 的目录路径"""
    return os.path.dirname(os.path.abspath(__file__))


def get_assets_dir() -> str:
    """获取 assets 目录路径"""
    assets_dir = os.path.join(get_skill_dir(), 'assets')
    os.makedirs(assets_dir, exist_ok=True)
    return assets_dir


def get_target_date_str():
    """获取目标日期字符串（因为任务在午夜执行，分析前一天）"""
    now = datetime.now(timezone(timedelta(hours=8)))
    target = now - timedelta(days=1)
    return target.strftime('%Y-%m-%d')


def load_history(date_str):
    """加载指定日期的 HISTORY 文件"""
    history_file = get_project_root().parent / 'HISTORY' / f'{date_str}.json'
    if not history_file.exists():
        return []
    
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取历史记录失败: {e}")
        return []


def analyze_history(records):
    """分析对话记录，提取关键信息"""
    if not records:
        return {
            'total_records': 0,
            'topics': [],
            'important_points': [],
        }
    
    total = len(records)
    topics = set()
    important_points = []
    
    for record in records:
        user_input = record.get('user_input', '')
        bot_response = record.get('bot_response', '')
        
        # 基于内容简单分类主题
        if any(kw in user_input for kw in ['源码', '代码', '位置', '文件', '目录']):
            topics.add('源码/代码相关')
        if any(kw in user_input for kw in ['记忆', 'history', '记录', '搜索']):
            topics.add('记忆/记录管理')
        if any(kw in user_input for kw in ['技能', '功能', '能做什么']):
            topics.add('功能/技能咨询')
        if any(kw in user_input for kw in ['ls', 'cd', 'pwd', 'find', 'cat']):
            topics.add('文件系统操作')
        if any(kw in user_input for kw in ['定时任务', 'scheduler', '分析']):
            topics.add('任务/调度管理')
        if any(kw in user_input for kw in ['飞书', 'feishu', '发送']):
            topics.add('飞书消息相关')
        if any(kw in user_input for kw in ['交易', 'btc', '策略', '回测']):
            topics.add('交易/策略相关')
        
        # 记录重要对话（用户提出的问题）
        if user_input and len(user_input) > 1:
            important_points.append(user_input[:80])
    
    return {
        'total_records': total,
        'topics': list(topics),
        'important_points': important_points[-20:],  # 最近20条
    }


def save_to_memory(date_str, analysis):
    """保存分析结果到 local-memory"""
    storage_dir = get_project_root() / 'local_memory'
    memory = MemoryManager(storage_dir=str(storage_dir))
    
    summary = f"""每日HISTORY对话分析报告 - {date_str}
对话记录总数: {analysis['total_records']} 条
涉及主题: {', '.join(analysis['topics']) if analysis['topics'] else '无'}

用户互动摘要:
{chr(10).join(['- ' + p for p in analysis['important_points']]) if analysis['important_points'] else '无'}
"""
    
    memory_id = memory.save(
        content=summary,
        category="daily_history_analysis",
        tags=["日报", "HISTORY分析", "对话记录", date_str],
        importance=4
    )
    
    return memory_id


def generate_report(date_str, analysis):
    """生成报告"""
    report = f"""╔══════════════════════════════════════════════════════════╗
║     📊 每日 HISTORY 对话分析报告 - {date_str}            ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  📈 数据统计:                                             ║
║     • 对话记录总数: {analysis['total_records']:>3} 条                         ║
║                                                          ║
║  🏷️  涉及主题:                                            ║
"""
    if analysis['topics']:
        for topic in analysis['topics']:
            report += f"║     • {topic:<20}                     ║\n"
    else:
        report += "║     • 无                                                  ║\n"
    
    report += """║                                                          ║
║  ⭐ 互动摘要（最近10条）:                                 ║
"""
    if analysis['important_points']:
        for point in analysis['important_points'][-10:]:
            point = point[:45]
            report += f"║     • {point:<45}  ║\n"
    else:
        report += "║     • 无                                                  ║\n"
    
    report += """║                                                          ║
║  ✅ 分析完成！结果已保存到记忆中                          ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""
    return report


def run(date_str=None):
    """
    执行每日 HISTORY 分析
    
    Returns:
        (report_text, memory_id, report_path)
    """
    if date_str is None:
        date_str = get_target_date_str()
    
    print(f"🤖 启动每日 HISTORY 对话分析...\n")
    print(f"📅 分析日期: {date_str}")
    
    # 1. 加载历史记录
    records = load_history(date_str)
    print(f"   ✓ 共加载 {len(records)} 条对话记录")
    
    if not records:
        print("   ⚠️ 没有找到历史记录，跳过分析")
        return f"📅 {date_str} 无对话记录", None, None
    
    # 2. 分析记录
    analysis = analyze_history(records)
    print(f"   ✓ 分析完成，涉及 {len(analysis['topics'])} 个主题")
    
    # 3. 保存到记忆
    memory_id = save_to_memory(date_str, analysis)
    print(f"   ✓ 已保存到记忆系统 (ID: {memory_id})")
    
    # 4. 生成报告
    report = generate_report(date_str, analysis)
    print(report)
    
    # 5. 保存报告到 skill assets 文件夹
    assets_dir = get_assets_dir()
    report_file = os.path.join(assets_dir, f"daily_history_report_{date_str}.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"📄 报告已保存: {report_file}")
    
    return report, memory_id, report_file


def main():
    """命令行入口"""
    report, memory_id, report_path = run()
    return report, memory_id, report_path


if __name__ == '__main__':
    main()
