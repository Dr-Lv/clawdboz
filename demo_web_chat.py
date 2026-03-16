#!/usr/bin/env python3
"""
Web Chat 功能演示
验证多 Bot + Web 界面功能
支持 WebChat MCP 模式（定时任务直接发送到本地聊天页面）
"""

import os
import sys

# 添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clawdboz import BotManager


def demo():
    """演示 Web Chat 功能"""
    print("="*60)
    print("Clawdboz v3.0 Web Chat 演示")
    print("="*60)
    
    # 启用 WebChat MCP 模式（定时任务发送到本地页面而非飞书）
    os.environ['CLAWDBOZ_MCP_MODE'] = 'webchat'
    print("\n[0] MCP 模式: WebChat (本地聊天页面)")
    
    # 使用项目根目录下的 WORKPLACE（bot 代码所在目录）
    # 默认路径：与 clawdboz/web/server.py 中的 _get_default_workplace() 一致
    project_root = os.path.dirname(os.path.abspath(__file__))
    workplace = os.path.join(project_root, "WORKPLACE")
    
    try:
        print(f"\n[1] 创建 BotManager")
        print(f"    项目根目录: {project_root}")
        print(f"    工作目录: {workplace}")
        manager = BotManager(base_workplace=workplace)
        
        print("\n[2] 注册多个 Bot（使用模拟凭证）")
        
        # Bot 1: 代码助手
        try:
            bot1 = manager.register(
                "code-assistant",
                "cli_test_code123",
                "test_secret_code",
                system_prompt="你是代码助手，擅长编程"
            )
            print("    ✓ code-assistant 已注册")
        except Exception as e:
            print(f"    ⚠ code-assistant: {e}")
        
        # Bot 2: 文档助手
        try:
            bot2 = manager.register(
                "doc-writer",
                "cli_test_doc456",
                "test_secret_doc",
                system_prompt="你是文档助手，擅长写作"
            )
            print("    ✓ doc-writer 已注册")
        except Exception as e:
            print(f"    ⚠ doc-writer: {e}")
        
        # Bot 3: 运维助手
        try:
            bot3 = manager.register(
                "ops-bot",
                "cli_test_ops789",
                "test_secret_ops",
                system_prompt="你是运维助手，擅长系统管理"
            )
            print("    ✓ ops-bot 已注册")
        except Exception as e:
            print(f"    ⚠ ops-bot: {e}")
        
        # Bot 4: 测试助手
        try:
            bot4 = manager.register(
                "test-bot",
                "cli_test_test101",
                "test_secret_test",
                system_prompt="你是测试助手，擅长软件测试和质量保证"
            )
            print("    ✓ test-bot 已注册")
        except Exception as e:
            print(f"    ⚠ test-bot: {e}")
        
        # Bot 5: 数据分析助手
        try:
            bot5 = manager.register(
                "data-analyst",
                "cli_test_data202",
                "test_secret_data",
                system_prompt="你是数据分析助手，擅长数据处理和可视化"
            )
            print("    ✓ data-analyst 已注册")
        except Exception as e:
            print(f"    ⚠ data-analyst: {e}")
        
        print(f"\n[3] 验证工作目录隔离")
        for bot_id in ["code-assistant", "doc-writer", "ops-bot", "test-bot", "data-analyst"]:
            bot_dir = os.path.join(workplace, bot_id)
            config_file = os.path.join(bot_dir, "config.json")
            
            if os.path.exists(config_file):
                import json
                with open(config_file) as f:
                    cfg = json.load(f)
                print(f"    ✓ {bot_id}/")
                print(f"      工作目录: {cfg['paths']['workplace']}")
                print(f"      App ID: {cfg['feishu']['app_id'][:15]}...")
        
        # 检查 Web 依赖
        print("\n[4] 检查 Web 依赖")
        try:
            import fastapi
            import uvicorn
            print("    ✓ fastapi 已安装")
            print("    ✓ uvicorn 已安装")
            has_web = True
        except ImportError:
            print("    ✗ 缺少 Web 依赖")
            print("      安装命令: pip install fastapi uvicorn")
            has_web = False
        
        if has_web:
            print("\n[5] 启动 Web 服务器（按 Ctrl+C 停止）")
            print("-"*60)
            
            from clawdboz.web import start_web_chat
            
            # 启动 Web 服务（非阻塞），使用固定 token 便于访问
            # 传递 base_workplace 以启用新的多级 workspace 架构
            server = start_web_chat(
                manager.bots, 
                port=8080, 
                auth_token="demo-token-123456",
                base_workplace=workplace
            )
            
            # 将访问信息写入文件
            with open('/tmp/web_chat_access.info', 'w') as f:
                f.write(f"token=demo-token-123456\n")
                f.write(f"url=http://localhost:8080/static/index.html?token=demo-token-123456\n")
            
            print("-"*60)
            print("\n提示:")
            print("  1. 打开浏览器访问上述 URL")
            print("  2. 在左侧选择一个或多个 Bot")
            print("  3. 输入消息测试单聊/群聊")
            print("\n按 Ctrl+C 停止服务器\n")
            
            # 保持运行
            import time
            while True:
                time.sleep(1)
        else:
            print("\n[!] 无法启动 Web 服务器，请先安装依赖")
            
    except KeyboardInterrupt:
        print("\n\n用户停止")
    except Exception as e:
        print(f"\n[!] 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"\n[信息] 工作目录保留: {workplace}")


if __name__ == "__main__":
    demo()
