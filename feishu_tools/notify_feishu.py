#!/usr/bin/env python3
"""
飞书通知工具 - 用于运维检查和修复状态通知
可以独立运行，不需要 Bot 进程
"""

import sys
import os
import json
import requests

# 导入 src 中的配置模块
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.config import PROJECT_ROOT, CONFIG, get_absolute_path

# 飞书应用配置
feishu_config = CONFIG.get('feishu', {})
APP_ID = feishu_config.get('app_id')
APP_SECRET = feishu_config.get('app_secret')


def get_tenant_access_token() -> str:
    """获取 tenant_access_token"""
    try:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        resp = requests.post(url, json={
            "app_id": APP_ID,
            "app_secret": APP_SECRET
        }, timeout=30)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("tenant_access_token")
        else:
            print(f"获取 token 失败: {data}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"获取 token 异常: {e}", file=sys.stderr)
        return None


def get_chat_info_from_context():
    """从上下文文件获取聊天信息"""
    paths_config = CONFIG.get('paths', {})
    context_file = get_absolute_path(paths_config.get('context_file', 'WORKPLACE/mcp_context.json'))
    try:
        if os.path.exists(context_file):
            with open(context_file, 'r') as f:
                context = json.load(f)
                return {
                    'chat_id': context.get('chat_id'),
                    'chat_type': context.get('chat_type', 'group')
                }
    except Exception as e:
        print(f"读取上下文失败: {e}", file=sys.stderr)
    return None


def send_message(receive_id: str, msg_type: str, content: dict, receive_id_type: str = "chat_id"):
    """发送消息到飞书"""
    token = get_tenant_access_token()
    if not token:
        return False
    
    try:
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        params = {"receive_id_type": receive_id_type}
        
        body = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content)
        }
        
        resp = requests.post(url, headers=headers, params=params, json=body, timeout=30)
        result = resp.json()
        
        if result.get("code") == 0:
            print(f"消息发送成功")
            return True
        else:
            print(f"消息发送失败: {result}", file=sys.stderr)
            return False
            
    except Exception as e:
        print(f"发送消息异常: {e}", file=sys.stderr)
        return False


def send_text_card(title: str, content: str, status: str = "info"):
    """
    发送文本卡片消息
    
    Args:
        title: 卡片标题
        content: 卡片内容（支持 Markdown）
        status: 状态颜色 (success/warning/error/info)
    """
    # 状态颜色映射
    color_map = {
        "success": "green",
        "warning": "orange",
        "error": "red",
        "info": "blue"
    }
    
    # 获取聊天信息
    chat_info = get_chat_info_from_context()
    if not chat_info or not chat_info['chat_id']:
        print("无法获取聊天信息", file=sys.stderr)
        return False
    
    chat_id = chat_info['chat_id']
    # chat_type = chat_info['chat_type']
    
    # 飞书 API：群聊和单聊都使用 chat_id 作为 receive_id_type
    receive_id_type = "chat_id"
    
    # 构建卡片内容
    card_content = {
        "config": {
            "wide_screen_mode": True
        },
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"🤖 Bot 运维通知 - {title}"
            },
            "template": color_map.get(status, "blue")
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": content
                }
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "时间: --"
                    }
                ]
            }
        ]
    }
    
    # 添加时间
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    card_content["elements"][1]["elements"][0]["content"] = f"🕐 {now}"
    
    return send_message(chat_id, "interactive", card_content, receive_id_type)


def notify_check_start():
    """通知：开始检查"""
    content = """开始执行运维检查，请稍候...

检查项目：
• Bot 进程状态
• WebSocket 连接
• 日志错误
• MCP 配置
• Skills 状态
• 虚拟环境"""
    
    return send_text_card("检查开始", content, "info")


def notify_issues_found(issues: str):
    """通知：发现问题"""
    content = f"""⚠️ **检查发现以下问题：**

{issues}

🔧 **正在调用 Kimi 进行自动修复...**
请稍候，修复完成后会再次通知。"""
    
    return send_text_card("发现问题", content, "warning")


def notify_repair_success():
    """通知：修复成功"""
    content = """✅ **问题已修复完成！**

Bot 已恢复正常运行状态。
如有疑问请检查日志或联系管理员。"""
    
    return send_text_card("修复完成", content, "success")


def notify_repair_failed(error: str):
    """通知：修复失败"""
    content = f"""❌ **自动修复失败**

错误信息：
```
{error}
```

请手动检查 Bot 状态或联系管理员处理。"""
    
    return send_text_card("修复失败", content, "error")


def notify_check_passed():
    """通知：检查通过"""
    content = """✅ **运维检查完成**

所有检查项目正常，Bot 运行良好！

检查项目：
• ✅ Bot 进程正常
• ✅ WebSocket 连接正常
• ✅ 无错误日志
• ✅ MCP 配置正常
• ✅ 虚拟环境正常"""
    
    return send_text_card("检查通过", content, "success")


def main():
    if len(sys.argv) < 2:
        print("Usage: python notify_feishu.py <command> [args]", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print("  check_start          - 通知检查开始", file=sys.stderr)
        print("  issues_found <text>  - 通知发现问题", file=sys.stderr)
        print("  repair_success       - 通知修复成功", file=sys.stderr)
        print("  repair_failed <msg>  - 通知修复失败", file=sys.stderr)
        print("  check_passed         - 通知检查通过", file=sys.stderr)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "check_start":
        notify_check_start()
    elif command == "issues_found":
        issues = sys.argv[2] if len(sys.argv) > 2 else "未知问题"
        notify_issues_found(issues)
    elif command == "repair_success":
        notify_repair_success()
    elif command == "repair_failed":
        error = sys.argv[2] if len(sys.argv) > 2 else "未知错误"
        notify_repair_failed(error)
    elif command == "check_passed":
        notify_check_passed()
    else:
        print(f"未知命令: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
